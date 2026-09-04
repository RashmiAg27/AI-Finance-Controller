"""Tool-layer tests: these exercise app.agent.tools directly against a
seeded batch, with no LLM involved -- verifying the tools return correct,
evidence-rich data and that tenant scoping actually blocks cross-client
access, independent of whether an LLM provider is configured."""
import random
from datetime import date
from pathlib import Path

import pytest

from app.agent.tools import ToolContext, ToolScopeError, execute_tool, get_batch_status, get_cash_position
from app.domains.batches import service as batch_service
from app.domains.clients import config_loader
from app.domains.clients import service as client_service
from app.domains.ingestion import service as ingestion_service
from app.synthetic import generator as gen
from app.synthetic import scenarios as sc

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def _seed_batch(db_session, tmp_path, client_code: str, scenarios: list[sc.Scenario]):
    client = client_service.create_client(db_session, code=client_code, name=client_code)
    config = config_loader.load_config_version(db_session, client_id=client.id, raw_yaml=_load_yaml(client_code))
    config_loader.activate_config_version(db_session, config_version_id=config.id)
    db_session.commit()

    batch = batch_service.create_batch(db_session, client_id=client.id, batch_code=f"{client_code}-agent")
    db_session.commit()

    written = gen.generate_batch_files(scenarios, client_code, batch.batch_code, tmp_path)
    for source_id, path in written.items():
        data_source = next(ds for ds in _data_sources(db_session, client.id) if ds.source_id == source_id)
        ingestion_service.store_uploaded_file(
            db_session, batch=batch, client=client, data_source=data_source,
            filename=path.name, content=path.read_bytes(),
        )
    db_session.commit()

    batch_service.mark_files_complete(db_session, batch)
    db_session.commit()
    batch_service.process_batch(db_session, batch)
    db_session.commit()
    return client, batch


def _data_sources(db_session, client_id):
    from sqlalchemy import select
    from app.models.data_source import DataSource

    return list(db_session.execute(select(DataSource).where(DataSource.client_id == client_id)).scalars())


@pytest.fixture()
def seeded_two_clients(db_session, tmp_path):
    base_date = date(2026, 9, 1)
    client_a, batch_a = _seed_batch(db_session, tmp_path / "a", "client_a", [
        sc.client_a_exact_match(1, base_date, random.Random(1)),
        sc.client_a_missing_external_record(1, base_date, random.Random(2)),
    ])
    client_b, batch_b = _seed_batch(db_session, tmp_path / "b", "client_b", [
        sc.client_b_exact_match(1, base_date, random.Random(3)),
    ])
    return {"client_a": client_a, "batch_a": batch_a, "client_b": client_b, "batch_b": batch_b}


def test_get_batch_status_unscoped(db_session, seeded_two_clients):
    ctx = ToolContext(db=db_session, scope_client_id=None)
    result = get_batch_status(ctx, seeded_two_clients["batch_a"].id)
    assert result["status"] == "CLOSED"
    assert result["client_id"] == seeded_two_clients["client_a"].id


def test_tenant_scoping_blocks_cross_client_access(db_session, seeded_two_clients):
    ctx = ToolContext(db=db_session, scope_client_id=seeded_two_clients["client_a"].id)

    # in-scope access works
    ok = get_batch_status(ctx, seeded_two_clients["batch_a"].id)
    assert ok["status"] == "CLOSED"

    # cross-client access is refused, not silently allowed
    with pytest.raises(ToolScopeError):
        get_batch_status(ctx, seeded_two_clients["batch_b"].id)

    # cash position tool enforces the same scoping
    with pytest.raises(ToolScopeError):
        get_cash_position(ctx, seeded_two_clients["client_b"].id)


def test_execute_tool_returns_error_dict_not_exception_for_scope_violation(db_session, seeded_two_clients):
    ctx = ToolContext(db=db_session, scope_client_id=seeded_two_clients["client_a"].id)
    result = execute_tool(ctx, "get_batch_status", {"batch_id": seeded_two_clients["batch_b"].id})
    assert "error" in result


def test_exception_summary_has_evidence_and_amount_impact(db_session, seeded_two_clients):
    ctx = ToolContext(db=db_session, scope_client_id=None)
    summary = execute_tool(ctx, "get_exception_summary", {"batch_id": seeded_two_clients["batch_a"].id, "top_n": 5})
    assert summary["open_exception_count"] == 1
    assert summary["by_type"]["MISSING_EXTERNAL_RECORD"] == 1
    largest = summary["largest_exceptions"][0]
    assert largest["likely_cause"]
    assert largest["amount_impact"]


def test_get_tax_rule_reports_verification_status(db_session, seeded_two_clients):
    ctx = ToolContext(db=db_session, scope_client_id=None)
    result = execute_tool(ctx, "get_tax_rule", {"rule_id": "GST_ON_PAYMENT_GATEWAY_FEE_V1"})
    assert result["verification_status"] == "VERIFIED"
    assert result["source_reference"]
    assert result["source_url"]


def test_find_transaction_by_reference(db_session, seeded_two_clients):
    ctx = ToolContext(db=db_session, scope_client_id=None)
    from sqlalchemy import select
    from app.models.transaction import TransactionIdentifier

    order_id_ident = db_session.execute(
        select(TransactionIdentifier).where(TransactionIdentifier.identifier_type == "ORDER_ID")
    ).scalars().first()
    result = execute_tool(ctx, "find_transaction_by_reference", {
        "client_id": seeded_two_clients["client_b"].id, "reference": order_id_ident.value_normalized,
    })
    assert result["matches"]
