"""M3 smoke test: a gross internal amount and a net gateway settlement with
no shared reference should resolve via Pass 5 (fee/tax explained), citing the
verified GST rule, rather than falling through to an exception."""
import random
from datetime import date
from pathlib import Path

from app.synthetic import generator as gen
from app.synthetic import scenarios as sc

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def test_client_b_fee_tax_explained_discrepancy(api_client, tmp_path):
    base_date = date(2026, 9, 1)
    scenarios = [
        sc.client_b_exact_match(1, base_date, random.Random(1)),
        sc.client_b_fee_adjusted_settlement(1, base_date, random.Random(2)),
    ]

    resp = api_client.post("/api/v1/clients", json={"code": "client_b", "name": "Client B"})
    client_id = resp.json()["id"]
    api_client.post(f"/api/v1/clients/{client_id}/config-versions", json={"raw_yaml": _load_yaml("client_b")})
    api_client.post(f"/api/v1/clients/{client_id}/config-versions/1/activate")

    batch_code = "client_b-m3"
    resp = api_client.post(f"/api/v1/clients/{client_id}/batches", json={"batch_code": batch_code})
    batch_id = resp.json()["id"]

    written = gen.generate_batch_files(scenarios, "client_b", batch_code, tmp_path)
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

    runs = api_client.get(f"/api/v1/batches/{batch_id}/reconciliation-runs").json()
    stats = runs[0]["stats_json"]
    assert stats["matches_by_pass"].get("5") == 1
    assert stats["unmatched_internal"] == 0
    assert stats["unmatched_external"] == 0

    matches = api_client.get(f"/api/v1/batches/{batch_id}/matches").json()
    fee_tax_matches = [m for m in matches if m["match_type"] == "EXPLAINED_BY_FEE_TAX"]
    assert len(fee_tax_matches) == 1
    match = fee_tax_matches[0]
    assert match["cardinality"] == "ONE_TO_ONE"

    evidence_types = {e["evidence_type"] for e in match["evidence"]}
    assert {"AMOUNT_COMPARISON", "TAX_RULE_APPLIED", "DATE_COMPARISON"} <= evidence_types

    tax_rule_evidence = next(e for e in match["evidence"] if e["evidence_type"] == "TAX_RULE_APPLIED")
    assert tax_rule_evidence["source_value"] == "GST_ON_PAYMENT_GATEWAY_FEE_V1"
    assert tax_rule_evidence["detail_json"]["verification_status"] == "VERIFIED"
    assert tax_rule_evidence["detail_json"]["source_reference"]

    amount_evidence = next(e for e in match["evidence"] if e["evidence_type"] == "AMOUNT_COMPARISON")
    detail = amount_evidence["detail_json"]
    gross = float(detail["gross_amount"])
    fee = float(detail["fee_amount"])
    tax = float(detail["tax_amount"])
    net = float(detail["expected_net"])
    assert round(gross - fee - tax, 2) == round(net, 2)
    assert round(fee, 2) == round(gross * 0.02, 2)
    assert round(tax, 2) == round(fee * 0.18, 2)
