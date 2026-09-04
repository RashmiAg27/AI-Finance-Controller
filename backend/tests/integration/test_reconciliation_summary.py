"""app.domains.batches.summary.build_summary is the canonical, backend-
computed reconciliation outcome the agent presents instead of aggregating
raw tool JSON itself. The real bug it exists to prevent: a duplicate
posting produces TWO Exception_ rows (one per side, see
app.domains.exceptions.classifier._duplicates_by_canonical_reference),
each carrying the FULL transaction amount -- summing amount_impact across
open exceptions naively (as the older ad-hoc tool code used to) counts that
one duplicate pair's exposure twice. This test drives the exact same
scenario mix as test_m5a_exceptions.py (which independently confirms two
DUPLICATE rows are created) through to a summary and asserts the money and
counts it reports are de-duplicated.
"""
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.agent.tools import ToolContext, execute_tool
from app.domains.batches import summary as summary_service
from app.synthetic import generator as gen
from app.synthetic import scenarios as sc

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def test_duplicate_pair_is_one_issue_not_two(api_client, db_session, tmp_path):
    base_date = date(2026, 9, 1)
    scenarios = [
        sc.client_a_exact_match(1, base_date, random.Random(1)),
        sc.client_a_missing_external_record(1, base_date, random.Random(2)),
        sc.client_a_duplicate_posting(1, base_date, random.Random(3)),
    ]

    resp = api_client.post("/api/v1/clients", json={"code": "client_a", "name": "Client A"})
    client_id = resp.json()["id"]
    api_client.post(f"/api/v1/clients/{client_id}/config-versions", json={"raw_yaml": _load_yaml("client_a")})
    api_client.post(f"/api/v1/clients/{client_id}/config-versions/1/activate")

    batch_code = "client_a-summary"
    resp = api_client.post(f"/api/v1/clients/{client_id}/batches", json={"batch_code": batch_code})
    batch_id = resp.json()["id"]

    written = gen.generate_batch_files(scenarios, "client_a", batch_code, tmp_path)
    for source_id, path in written.items():
        with path.open("rb") as f:
            resp = api_client.post(
                f"/api/v1/batches/{batch_id}/files", params={"source_id": source_id}, files={"file": (path.name, f)}
            )
            assert resp.status_code == 200, resp.text

    api_client.post(f"/api/v1/batches/{batch_id}/files/complete")
    resp = api_client.post(f"/api/v1/batches/{batch_id}/process")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CLOSED"

    # Sanity check on the raw data this summary is built from -- confirms the
    # premise: two exception ROWS exist for the one duplicate posting.
    exceptions = api_client.get(f"/api/v1/batches/{batch_id}/exceptions").json()
    duplicate_rows = [e for e in exceptions if e["exception_type"] == "DUPLICATE"]
    assert len(duplicate_rows) == 2
    naive_sum = sum(float(e["amount_impact"]) for e in exceptions)

    result = summary_service.build_summary(db_session, batch_id)

    # One logical issue for the duplicate pair + one for the missing record --
    # not three, even though there are three Exception_ rows.
    assert result.exception_count == 2
    # Every transaction touched by an exception, counted once each: the two
    # duplicate-pair transactions plus the one missing-record transaction.
    assert result.affected_record_count == 3
    # The canonical total must be strictly less than naively summing every
    # row's amount_impact -- that sum double-counts the duplicate pair.
    assert float(result.canonical_amount_at_risk) < naive_sum

    # Both duplicate-pair rows carry the same amount_impact (the classifier
    # records the transaction's own amount on each side of a true duplicate),
    # so the canonical total is exactly one of them plus the unrelated
    # missing-record exception's amount -- never their sum.
    duplicate_amount = Decimal(duplicate_rows[0]["amount_impact"])
    assert Decimal(duplicate_rows[0]["amount_impact"]) == Decimal(duplicate_rows[1]["amount_impact"])
    missing_amount = Decimal(next(e["amount_impact"] for e in exceptions if e["exception_type"] == "MISSING_EXTERNAL_RECORD"))
    assert result.canonical_amount_at_risk == duplicate_amount + missing_amount

    # The duplicate pair's IssueGroup reports two affected records, not one
    # and not the raw row count of two rows summed as separate issues.
    duplicate_issue = next(g for g in result.top_issues if g.exception_type == "DUPLICATE")
    assert duplicate_issue.affected_record_count == 2
    assert duplicate_issue.amount_impact == duplicate_amount

    # The agent TOOL wrapper must expose the same canonical fields, JSON-safe
    # (Decimal -> str) and with completed_at already localized -- never a
    # raw UTC timestamp the model would have to convert itself.
    ctx = ToolContext(db=db_session, scope_client_id=client_id)
    tool_result = execute_tool(ctx, "get_reconciliation_summary", {"batch_id": batch_id})
    assert tool_result["exception_count"] == 2
    assert tool_result["affected_record_count"] == 3
    assert Decimal(tool_result["canonical_amount_at_risk"]) == duplicate_amount + missing_amount
    assert tool_result["batch_name"]
    assert "IST" in tool_result["completed_at"]
