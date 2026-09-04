"""Builds the synthetic demo dataset for both clients, runs the full
deterministic pipeline (M0-M7) through the real service layer, and prints
honest metrics computed from persisted results only -- never fabricated.

This is also how the demo database gets seeded: run it, then start the API
(`uvicorn app.main:app`) or frontend against the same backend/finance_controller.db
and data/ directory to explore the same batches this script just reconciled.

Usage: python scripts/evaluate_against_ground_truth.py [--seed 42] [--filler-count 15]
"""
import argparse
import sys
import tempfile
import time
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, create_all_tables, engine  # noqa: E402
from app.domains.batches import service as batch_service  # noqa: E402
from app.domains.clients import config_loader, service as client_service  # noqa: E402
from app.domains.tax.rules_seed import ensure_seed_rules  # noqa: E402
from app.models.exception_ import Exception_, ExceptionTransaction  # noqa: E402
from app.models.reconciliation import ReconciliationMatch, ReconciliationMatchTransaction  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402
from app.synthetic import generator as gen  # noqa: E402
from app.synthetic import scenarios as sc  # noqa: E402

CONFIGS_ROOT = Path(__file__).resolve().parents[1] / "configs" / "clients"

# Which scenarios are expected to fully resolve via a CONFIRMED match vs land
# in the exception queue -- the ground-truth expectation this script checks
# actual results against.
_EXPECTED_MATCH_SCENARIOS = {
    "EXACT_IDENTIFIER_MATCH", "NORMALIZED_REFERENCE_MATCH", "TIMING_DIFFERENCE",
    "COUNTERPARTY_VARIATION", "SPLIT_SETTLEMENT_ONE_TO_MANY", "FEE_ADJUSTED_SETTLEMENT",
    "BUNDLED_SETTLEMENT_MANY_TO_ONE", "REFERENCE_MATCHED_UNEXPLAINED_VARIANCE",
}


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def _run_client_batch(db: Session, client_code: str, batch_code: str, scenarios: list[sc.Scenario]) -> dict:
    client = client_service.create_client(db, code=client_code, name=client_code)
    config = config_loader.load_config_version(db, client_id=client.id, raw_yaml=_load_yaml(client_code))
    config_loader.activate_config_version(db, config_version_id=config.id)
    db.commit()

    batch = batch_service.create_batch(db, client_id=client.id, batch_code=batch_code)
    db.commit()

    # Fixture files are generated into a scratch staging directory, separate
    # from the app's own data/raw storage -- store_uploaded_file() below is
    # what actually places them under settings.data_root, exactly like a
    # real HTTP upload would, so the two must never share a path.
    staging_dir = Path(tempfile.mkdtemp(prefix="afc_seed_"))
    written = gen.generate_batch_files(scenarios, client_code, batch_code, staging_dir)
    for source_id, path in written.items():
        data_source = next(ds for ds in db_config_data_sources(db, client.id) if ds.source_id == source_id)
        content = path.read_bytes()
        from app.domains.ingestion import service as ingestion_service

        ingestion_service.store_uploaded_file(
            db, batch=batch, client=client, data_source=data_source, filename=path.name, content=content
        )
    db.commit()

    batch_service.mark_files_complete(db, batch)
    db.commit()

    start = time.perf_counter()
    batch_service.process_batch(db, batch)
    db.commit()
    elapsed = time.perf_counter() - start

    return {"client": client, "batch": batch, "elapsed_seconds": elapsed}


def db_config_data_sources(db: Session, client_id: str):
    from app.models.data_source import DataSource
    from sqlalchemy import select

    return list(db.execute(select(DataSource).where(DataSource.client_id == client_id)).scalars())


def _actual_outcome_by_economic_id(db: Session, batch_id: str) -> dict[str, dict]:
    from sqlalchemy import select

    txns = list(db.execute(select(Transaction).where(Transaction.batch_id == batch_id)).scalars())
    txn_by_id = {t.id: t for t in txns}
    eco_by_txn_id = {t.id: t.metadata_json.get("economic_transaction_id") for t in txns}

    outcomes: dict[str, dict] = {
        eco_id: {"match_type": None, "cardinality": None, "exception_type": None}
        for eco_id in set(eco_by_txn_id.values()) if eco_id
    }

    match_links = list(
        db.execute(
            select(ReconciliationMatchTransaction, ReconciliationMatch)
            .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchTransaction.match_id)
            .where(ReconciliationMatchTransaction.transaction_id.in_(txn_by_id.keys()))
        ).all()
    )
    for link, match in match_links:
        eco_id = eco_by_txn_id.get(link.transaction_id)
        if eco_id and outcomes.get(eco_id, {}).get("match_type") is None:
            outcomes[eco_id]["match_type"] = match.match_type
            outcomes[eco_id]["cardinality"] = match.cardinality

    exception_links = list(
        db.execute(
            select(ExceptionTransaction, Exception_)
            .join(Exception_, Exception_.id == ExceptionTransaction.exception_id)
            .where(ExceptionTransaction.transaction_id.in_(txn_by_id.keys()))
        ).all()
    )
    for link, exc in exception_links:
        eco_id = eco_by_txn_id.get(link.transaction_id)
        if eco_id:
            outcomes.setdefault(eco_id, {"match_type": None, "cardinality": None, "exception_type": None})
            outcomes[eco_id]["exception_type"] = exc.exception_type

    return outcomes, len(txns)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--filler-count", type=int, default=15)
    args = parser.parse_args()

    print("Resetting schema and seeding verified tax rules...")
    Base.metadata.drop_all(bind=engine)
    create_all_tables()
    db = SessionLocal()
    ensure_seed_rules(db)
    db.commit()

    base_date = date.today()
    all_scenarios = gen.default_scenarios(args.seed, base_date, args.filler_count)

    batch_code = base_date.isoformat()
    total_elapsed = 0.0
    all_outcomes: dict[str, dict] = {}
    scenario_by_eco_id = {s.economic_transaction_id: s for s in all_scenarios}
    total_txn_count = 0

    for client_code in ("client_a", "client_b"):
        client_scenarios = [s for s in all_scenarios if s.client_code == client_code]
        print(f"\n=== {client_code}: {len(client_scenarios)} scenarios ===")
        result = _run_client_batch(db, client_code, batch_code, client_scenarios)
        total_elapsed += result["elapsed_seconds"]
        outcomes, txn_count = _actual_outcome_by_economic_id(db, result["batch"].id)
        all_outcomes.update(outcomes)
        total_txn_count += txn_count
        print(f"  batch {result['batch'].batch_code}: {result['batch'].status}, "
              f"{txn_count} transactions, {result['elapsed_seconds']:.3f}s")

    # ---- honest metrics, computed only from persisted outcomes ----
    total_scenarios = len(scenario_by_eco_id)
    correctly_matched = 0
    correctly_exceptioned = 0
    incorrectly_resolved = 0
    false_positive_groups = 0
    exception_type_counts: Counter = Counter()
    match_type_counts: Counter = Counter()

    for eco_id, scenario in scenario_by_eco_id.items():
        outcome = all_outcomes.get(eco_id, {})
        expects_match = scenario.scenario_name in _EXPECTED_MATCH_SCENARIOS
        if outcome.get("match_type"):
            match_type_counts[outcome["match_type"]] += 1
            if expects_match:
                correctly_matched += 1
            else:
                incorrectly_resolved += 1  # matched something that should have been an exception
        elif outcome.get("exception_type"):
            exception_type_counts[outcome["exception_type"]] += 1
            if not expects_match:
                correctly_exceptioned += 1
            else:
                incorrectly_resolved += 1  # should have matched but ended up an exception

    # False positive check: for every CONFIRMED match, do ALL its transactions
    # share the same economic_transaction_id? A match spanning >1 economic
    # event would be a genuine false-positive reconciliation.
    from sqlalchemy import select

    all_matches = list(db.execute(select(ReconciliationMatch)).scalars())
    for match in all_matches:
        links = list(
            db.execute(
                select(ReconciliationMatchTransaction).where(ReconciliationMatchTransaction.match_id == match.id)
            ).scalars()
        )
        eco_ids = set()
        for link in links:
            txn = db.get(Transaction, link.transaction_id)
            eco_ids.add(txn.metadata_json.get("economic_transaction_id"))
        if len(eco_ids) > 1:
            false_positive_groups += 1

    matchable_scenario_count = sum(
        1 for s in scenario_by_eco_id.values() if s.scenario_name in _EXPECTED_MATCH_SCENARIOS
    )
    auto_match_rate = sum(match_type_counts.values()) / total_scenarios if total_scenarios else 0.0
    exception_rate = sum(exception_type_counts.values()) / total_scenarios if total_scenarios else 0.0
    precision = correctly_matched / max(sum(match_type_counts.values()), 1)
    recall = correctly_matched / max(matchable_scenario_count, 1)

    print("\n" + "=" * 60)
    print("DETERMINISTIC PIPELINE -- GROUND TRUTH EVALUATION (M0-M7 baseline)")
    print("=" * 60)
    print(f"Total transactions processed:      {total_txn_count}")
    print(f"Total economic-event scenarios:    {total_scenarios}")
    print(f"Auto-matched (deterministic):       {sum(match_type_counts.values())} ({auto_match_rate:.1%})")
    print(f"Unresolved (exception queue):        {sum(exception_type_counts.values())} ({exception_rate:.1%})")
    print(f"Correctly resolved vs ground truth:  {correctly_matched + correctly_exceptioned}/{total_scenarios}")
    print(f"Incorrectly resolved vs ground truth: {incorrectly_resolved}")
    print(f"Precision (of matches made):         {precision:.1%}")
    print(f"Recall (of matchable scenarios):     {recall:.1%}")
    print(f"False-positive match groups:         {false_positive_groups} (transactions from >1 economic event linked together)")
    print(f"Total processing time:               {total_elapsed:.3f}s")
    print("\nMatch type breakdown:")
    for match_type, count in match_type_counts.most_common():
        print(f"  {match_type:40s} {count}")
    print("\nException type breakdown:")
    for exc_type, count in exception_type_counts.most_common():
        print(f"  {exc_type:40s} {count}")
    print("\nNote: ML-assisted matching (Pass 7 / M5b) is not yet implemented -- "
          "these numbers are the deterministic-only baseline it must be measured against.")


if __name__ == "__main__":
    main()
