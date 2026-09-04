"""Builds the demo world: two clients, their bank accounts, configurations,
import sources, configured batches, and the files waiting in each one.

Nothing here fabricates a *result* -- it fabricates the inputs an operations
team would actually receive, and leaves the batches for you (or the agent) to
run. The shape of the world lives in scripts/demo_world.py.

Usage:
    python scripts/seed_demo_world.py [--seed 42] [--run] [--business-date YYYY-MM-DD]
"""
import argparse
import csv
import io
import json
import random
import shutil
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import demo_world as world  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, create_all_tables, engine  # noqa: E402
from app.domains.batches import definitions as definitions_service  # noqa: E402
from app.domains.batches import runner, service as batch_service  # noqa: E402
from app.domains.clients import accounts as accounts_service  # noqa: E402
from app.domains.clients import config_loader, service as client_service  # noqa: E402
from app.domains.ingestion import import_sources as import_sources_domain  # noqa: E402
from app.domains.tax.rules_seed import ensure_seed_rules  # noqa: E402
from app.domains.tax.service import calculate_fee_and_tax  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.config_version import ClientConfiguration  # noqa: E402
from app.schemas.config import ClientConfigSchema  # noqa: E402
from app.synthetic import account_scenarios as acc  # noqa: E402
from app.synthetic import demo_scenarios as ds  # noqa: E402
from app.synthetic import generator as gen  # noqa: E402
from app.synthetic import scenarios as sc  # noqa: E402

CONFIGS_ROOT = Path(__file__).resolve().parents[1] / "configs" / "clients"


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def _serialize(client_code: str, source_id: str, rows: list[dict]) -> tuple[str, bytes]:
    extension, sheet_name = world.FILE_FORMATS[(client_code, source_id)]
    columns = gen._all_columns(rows)

    if extension == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, restval="", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return extension, buffer.getvalue().encode("utf-8")
    if extension == "json":
        return extension, json.dumps(rows, indent=2).encode("utf-8")
    if extension == "xlsx":
        buffer = io.BytesIO()
        pd.DataFrame(rows, columns=columns).fillna("").to_excel(buffer, sheet_name=sheet_name, index=False)
        return extension, buffer.getvalue()
    raise ValueError(f"unsupported extension {extension!r}")


def _drop_file(directory: Path, client_code: str, source_id: str, rows: list[dict],
               business_date: str) -> Path:
    """Writes one feed file into a landing area, named the way discovery
    expects: '<source_id>__<business date>.<ext>'."""
    extension, content = _serialize(client_code, source_id, rows)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{source_id}__{business_date}.{extension}"
    path.write_bytes(content)
    return path


def _rows_for(scenarios: list[sc.Scenario], source_id: str) -> list[dict]:
    rows: list[dict] = []
    for scenario in scenarios:
        rows.extend(scenario.rows_by_source.get(source_id, []))
    return rows


def _active_config(db: Session, client_code: str) -> ClientConfigSchema:
    client = db.execute(select(Client).where(Client.code == client_code)).scalar_one()
    row = db.execute(
        select(ClientConfiguration).where(
            ClientConfiguration.client_id == client.id, ClientConfiguration.status == "ACTIVE"
        )
    ).scalar_one()
    return ClientConfigSchema.model_validate(row.parsed_json)


# ---------------------------------------------------------------------------
# Scenario sets, one per configured batch
# ---------------------------------------------------------------------------

def _mrdn_hdfc(seed: int, base_date: date, filler: int) -> list[sc.Scenario]:
    rng = random.Random(seed)
    out = [sc.client_a_exact_match(i, base_date, rng) for i in range(1, filler + 1)]
    out += [
        sc.client_a_normalized_reference_match(1, base_date, rng),
        sc.client_a_timing_difference(1, base_date, rng),
        sc.client_a_counterparty_variation(1, base_date, rng),
        sc.client_a_split_settlement_one_to_many(1, base_date, rng),
        sc.client_a_missing_external_record(1, base_date, rng),
        sc.client_a_duplicate_posting(1, base_date, rng),
    ]
    return ds.retag(out, "MRDN")


def _mrdn_icici(seed: int, base_date: date) -> list[sc.Scenario]:
    rng = random.Random(seed + 11)
    out = [acc.mrdn_icici_exact_match(i, base_date, rng) for i in range(1, 10)]
    out.append(acc.mrdn_icici_outstanding_cheque(1, base_date, rng))
    return out


def _mrdn_sweeps(seed: int, base_date: date) -> list[sc.Scenario]:
    rng = random.Random(seed + 23)
    return [
        acc.mrdn_internal_sweep(1, base_date, rng,
                                from_account="HDFC_OPERATING", to_account="ICICI_OPERATING"),
        acc.mrdn_internal_sweep(2, base_date, rng,
                                from_account="HDFC_OPERATING", to_account="ICICI_OPERATING"),
        acc.mrdn_internal_sweep(3, base_date, rng,
                                from_account="HDFC_OPERATING", to_account="ICICI_OPERATING"),
    ]


def _mrdn_obligation(db: Session, seed: int, base_date: date) -> list[sc.Scenario]:
    rng = random.Random(seed + 29)
    config = _active_config(db, "MRDN")
    out = [ds.mrdn_obligation_exact_match(i, base_date, rng) for i in range(1, 9)]
    for i in range(1, 4):
        gross = Decimal(rng.randrange(15_000_00, 45_000_00)) / 100
        calc = calculate_fee_and_tax(db, gross, config.tax_fee_rules, instrument_type="EXCH_PAYOUT")
        out.append(ds.mrdn_obligation_charges_explained(i, base_date, rng, gross, calc.net_amount))
    out.append(ds.mrdn_obligation_missing_internal(1, base_date, rng))
    out.append(ds.mrdn_obligation_unexplained_variance(1, base_date, rng))
    return out


def _shyd_pg(db: Session, seed: int, base_date: date, filler: int) -> tuple[list[sc.Scenario], list[dict]]:
    """Returns the payment-settlement scenarios plus the settlement summaries
    the Settlement<->Bank cycle will later have to find in the bank."""
    rng = random.Random(seed + 43)
    out = [sc.client_b_exact_match(i, base_date, rng) for i in range(1, filler + 1)]
    out += [
        sc.client_b_bundled_settlement_many_to_one(1, base_date, rng),
        sc.client_b_reference_matched_unexplained_variance(1, base_date, rng),
    ]
    out = ds.retag(out, "SHYD")

    config = _active_config(db, "SHYD")
    settlements: list[dict] = []
    for i in range(1, 4):
        gross = Decimal(rng.randrange(600000, 2000000)) / 100
        calc = calculate_fee_and_tax(db, gross, config.tax_fee_rules, instrument_type="PAYMENT")
        out.append(_shyd_fee_scenario(i, base_date, rng, gross, calc.net_amount))
        settlements.append({"gross": gross, "net": calc.net_amount, "ref": f"SETL{770000 + i}"})
    return out, settlements


def _shyd_fee_scenario(seq: int, base_date: date, rng: random.Random,
                       gross: Decimal, net: Decimal) -> sc.Scenario:
    eco_id = f"SHYD-PG-CHARGES-{seq:04d}"
    customer = rng.choice(ds.BORROWERS)
    txn_date = base_date - timedelta(days=rng.randint(0, 3))
    internal_row = sc._tag({
        "InternalRef": f"COLLINT{seq:05d}",
        "OrderId": "",
        "PostedOn": txn_date.isoformat(),
        "Amount": str(gross),
        "DrCr": "CR",
        "CustomerName": customer,
        "Notes": "Provisional collection booked gross; MDR, GST, commission and TDS "
                 "deducted on settlement",
        "SettlementBatchRef": "",
    }, eco_id)
    gateway_row = sc._tag({
        "gateway_txn_id": f"PGBATCH{930000 + seq}",
        "order_id": "",
        "settled_at": f"{txn_date.isoformat()}T18:30:00",
        "net_amount": str(net),
        "entry_type": "settlement",
        "merchant_name": customer,
        "remarks": "aggregate settlement, MDR and GST on MDR, commission and TDS deducted",
        "batch_ref": "",
    }, eco_id)
    return sc.Scenario(
        scenario_name="FEE_ADJUSTED_SETTLEMENT",
        economic_transaction_id=eco_id,
        client_code="SHYD",
        rows_by_source={"internal_ledger": [internal_row], "payment_gateway": [gateway_row]},
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "payment_gateway"]},
    )


def _shyd_settlement_bank(seed: int, base_date: date, settlements: list[dict]) -> list[sc.Scenario]:
    rng = random.Random(seed + 51)
    return [
        acc.shyd_settlement_bank_credit(i, base_date, rng, gross=s["gross"], net=s["net"],
                                        settlement_ref=s["ref"])
        for i, s in enumerate(settlements, start=1)
    ]


def _shyd_nach(seed: int, base_date: date) -> list[sc.Scenario]:
    rng = random.Random(seed + 61)
    out = [ds.shyd_nach_successful_collection(i, base_date, rng) for i in range(1, 11)]
    out += [
        ds.shyd_nach_returned_mandate(1, base_date, rng),
        ds.shyd_nach_amount_break(1, base_date, rng),
        ds.shyd_nach_missing_internal(1, base_date, rng),
        ds.shyd_nach_missing_external(1, base_date, rng),
    ]
    return out


def _shyd_tax(seed: int, base_date: date) -> list[sc.Scenario]:
    rng = random.Random(seed + 71)
    return [
        acc.shyd_tax_challan(1, base_date, rng, tax_type="GST", amount=Decimal("184500.00")),
        acc.shyd_tax_challan(2, base_date, rng, tax_type="GST", amount=Decimal("46200.00")),
        acc.shyd_tax_challan(3, base_date, rng, tax_type="TDS", amount=Decimal("92750.00")),
        # A liability booked with no challan yet: an unpaid statutory dues break,
        # which is exactly what a tax reconciliation exists to surface.
        acc.shyd_tax_challan(4, base_date, rng, tax_type="TDS", amount=Decimal("31400.00"),
                             matched=False),
    ]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def seed_clients(db: Session) -> dict[str, Client]:
    clients: dict[str, Client] = {}
    for spec in world.CLIENTS:
        client = client_service.create_client(db, code=spec["code"], name=spec["name"])
        raw_yaml = (CONFIGS_ROOT / spec["code"] / "v1.yaml").read_text(encoding="utf-8")
        version = config_loader.load_config_version(db, client_id=client.id, raw_yaml=raw_yaml)
        config_loader.activate_config_version(db, config_version_id=version.id)
        clients[spec["code"]] = client
        print(f"  {spec['code']}: {spec['name']} -- config v{version.version} ACTIVE")
    db.commit()
    return clients


def seed_accounts(db: Session, clients: dict[str, Client]) -> dict[tuple[str, str], object]:
    created: dict[tuple[str, str], object] = {}
    for client_code, specs in world.BANK_ACCOUNTS.items():
        for spec in specs:
            row = accounts_service.create_account(db, client_id=clients[client_code].id, **spec)
            created[(client_code, spec["account_code"])] = row
            print(f"  {client_code}/{spec['account_code']:18s} {row.bank_name} {row.account_number_masked} "
                  f"[{row.purpose}]")
    db.commit()
    return created


def seed_import_sources(db: Session, clients: dict[str, Client]) -> dict[tuple[str, str], object]:
    created: dict[tuple[str, str], object] = {}
    for client_code, specs in world.IMPORT_SOURCES.items():
        for spec in specs:
            row = definitions_service.create_import_source(
                db, client_id=clients[client_code].id, code=spec["code"], name=spec["name"],
                kind=spec["kind"], connection=spec["connection"],
            )
            created[(client_code, spec["code"])] = row
            print(f"  {client_code}/{spec['code']:22s} [{spec['kind']:17s}] "
                  f"{import_sources_domain.describe_location(row, client_code)}")
    db.commit()
    return created


def seed_batch_definitions(db: Session, clients, accounts, import_sources) -> dict[str, object]:
    created: dict[str, object] = {}
    for client_code, specs in world.BATCH_DEFINITIONS.items():
        for spec in specs:
            account = accounts.get((client_code, spec["bank_account_code"])) if spec["bank_account_code"] else None
            row = definitions_service.create_definition(
                db, client_id=clients[client_code].id, code=spec["code"], name=spec["name"],
                description=spec["description"], batch_type=spec["batch_type"],
                reconciliation_type=spec["reconciliation_type"],
                bank_account_id=account.id if account else None,
                trigger_type=spec["trigger_type"], trigger_detail=spec["trigger_detail"],
                import_source_id=import_sources[(client_code, spec["import_source_code"])].id,
                source_ids=spec["source_ids"], cutoff_time=spec["cutoff_time"],
                sla_minutes=spec["sla_minutes"], owner_team=spec["owner_team"],
            )
            created[spec["code"]] = row
            account_label = account.account_number_masked if account else "(spans accounts)"
            print(f"  {spec['code']:24s} {spec['reconciliation_type']:20s} {account_label}")
    db.commit()
    return created


def drop_demo_files(db: Session, import_sources, *, seed: int, business_date: str, filler: int) -> None:
    base_date = date.fromisoformat(business_date)

    shyd_pg_scenarios, settlements = _shyd_pg(db, seed, base_date, filler)

    plan = [
        ("MRDN", "MRDN_LOCAL_HDFC", ["internal_ledger", "bank_statement"],
         _mrdn_hdfc(seed, base_date, filler)),
        ("MRDN", "MRDN_LOCAL_ICICI", ["internal_ledger", "icici_statement"],
         _mrdn_icici(seed, base_date)),
        ("MRDN", "MRDN_SFTP_CLEARING", ["internal_ledger", "exchange_obligation"],
         _mrdn_obligation(db, seed, base_date)),
        ("MRDN", "MRDN_EMAIL_TREASURY", ["treasury_ledger", "bank_statement", "icici_statement"],
         _mrdn_sweeps(seed, base_date)),
        ("SHYD", "SHYD_API_PG", ["internal_ledger", "payment_gateway"], shyd_pg_scenarios),
        ("SHYD", "SHYD_LOCAL_HDFC", ["internal_ledger", "bank_statement"],
         _shyd_settlement_bank(seed, base_date, settlements)),
        ("SHYD", "SHYD_EMAIL_NACH", ["internal_ledger", "nach_return"],
         _shyd_nach(seed, base_date)),
        ("SHYD", "SHYD_LOCAL_TAX", ["internal_ledger", "tax_challan"],
         _shyd_tax(seed, base_date)),
        # SHYD_LOCAL_DISBURSAL is left empty on purpose.
    ]

    for client_code, import_source_code, source_ids, scenarios in plan:
        import_source = import_sources[(client_code, import_source_code)]
        directory = import_sources_domain.landing_dir(import_source, client_code)
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        for source_id in source_ids:
            rows = _rows_for(scenarios, source_id)
            if not rows:
                continue
            path = _drop_file(directory, client_code, source_id, rows, business_date)
            print(f"  {client_code}/{import_source_code}: {path.name} ({len(rows)} rows)")

    empty = import_sources_domain.landing_dir(import_sources[("SHYD", "SHYD_LOCAL_DISBURSAL")], "SHYD")
    empty.mkdir(parents=True, exist_ok=True)
    print(f"  SHYD/SHYD_LOCAL_DISBURSAL: left empty at {empty}")


def run_ready_batches(db: Session, definitions: dict[str, object], business_date: str) -> None:
    for code, definition in definitions.items():
        state = definitions_service.definition_state(db, definition)
        if not state["data_available"]:
            print(f"  {code}: skipped ({state['state']}, missing {state['missing_source_ids']})")
            continue
        batch = batch_service.create_batch(
            db, client_id=definition.client_id,
            batch_code=definitions_service.next_batch_code(db, definition, business_date),
            actor="seed-script", batch_definition_id=definition.id, business_date=business_date,
            triggered_by_type="SCHEDULED",
        )
        db.commit()
        runner.submit(batch.id)
        print(f"  {code}: queued {batch.batch_code}")

    runner.wait_for_all(timeout=900)

    for code, definition in definitions.items():
        latest = definitions_service.latest_batch(db, definition.id)
        if latest is None:
            continue
        db.refresh(latest)
        detail = f" -- {latest.failure_reason}" if latest.failure_reason else ""
        print(f"  {code}: {latest.batch_code} {latest.status}{detail}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--filler-count", type=int, default=10)
    parser.add_argument("--business-date", type=str, default=date.today().isoformat())
    parser.add_argument("--run", action="store_true",
                        help="also execute every batch that has data waiting")
    args = parser.parse_args()

    print("Resetting schema, raw file storage, and verified tax rules...")
    Base.metadata.drop_all(bind=engine)
    create_all_tables()
    shutil.rmtree(settings.data_root / "raw", ignore_errors=True)

    db = SessionLocal()
    ensure_seed_rules(db)
    db.commit()

    print("\nClients and configurations")
    clients = seed_clients(db)

    print("\nBank accounts (the reconciliation units)")
    accounts = seed_accounts(db, clients)

    print("\nImport sources")
    import_sources = seed_import_sources(db, clients)

    print("\nConfigured batches")
    definitions = seed_batch_definitions(db, clients, accounts, import_sources)

    print("\nDropping fabricated feed files into each import source")
    drop_demo_files(db, import_sources, seed=args.seed,
                    business_date=args.business_date, filler=args.filler_count)

    if args.run:
        print("\nRunning every batch that has data")
        run_ready_batches(db, definitions, args.business_date)

    print("\nDone. Start the API with:  python -m uvicorn app.main:app --reload --port 8000")
    db.close()


if __name__ == "__main__":
    main()
