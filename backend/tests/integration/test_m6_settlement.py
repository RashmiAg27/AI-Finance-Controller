"""M6 smoke test: the fee-adjusted-settlement match from M3 produces a
Settlement whose component breakdown sums correctly to the observed net
credit, and a reference-matched pair with an undocumented deduction is
flagged as an unexplained variance (with a FEE_VARIANCE exception) rather
than silently accepted or wrongly explained by the fee/tax formula."""
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.synthetic import generator as gen
from app.synthetic import scenarios as sc

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def test_client_b_settlement_decomposition(api_client, tmp_path):
    base_date = date(2026, 9, 1)
    scenarios = [
        sc.client_b_fee_adjusted_settlement(1, base_date, random.Random(1)),
        sc.client_b_reference_matched_unexplained_variance(1, base_date, random.Random(2)),
    ]

    resp = api_client.post("/api/v1/clients", json={"code": "client_b", "name": "Client B"})
    client_id = resp.json()["id"]
    api_client.post(f"/api/v1/clients/{client_id}/config-versions", json={"raw_yaml": _load_yaml("client_b")})
    api_client.post(f"/api/v1/clients/{client_id}/config-versions/1/activate")

    batch_code = "client_b-m6"
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

    settlements = api_client.get(f"/api/v1/batches/{batch_id}/settlements").json()
    assert len(settlements) == 2

    fully_explained = [s for s in settlements if s["is_fully_explained"]]
    unexplained = [s for s in settlements if not s["is_fully_explained"]]
    assert len(fully_explained) == 1
    assert len(unexplained) == 1

    good = fully_explained[0]
    total_components = sum(Decimal(str(c["amount"])) for c in good["components"])
    assert round(Decimal(str(good["gross_amount"])) - total_components, 2) == round(Decimal(str(good["net_amount_observed"])), 2)
    component_types = {c["component_type"] for c in good["components"]}
    assert component_types == {"FEE", "TAX_ON_FEE"}
    tax_component = next(c for c in good["components"] if c["component_type"] == "TAX_ON_FEE")
    assert tax_component["tax_rule_id"] is not None

    bad = unexplained[0]
    assert bad["components"][0]["component_type"] == "OTHER_DEDUCTION"
    assert round(Decimal(str(bad["net_amount_observed"])), 2) == round(
        Decimal(str(bad["gross_amount"])) - Decimal("150.00"), 2
    )

    exceptions = api_client.get(f"/api/v1/batches/{batch_id}/exceptions").json()
    fee_variance = [e for e in exceptions if e["exception_type"] == "FEE_VARIANCE"]
    assert len(fee_variance) == 1
    assert Decimal(str(fee_variance[0]["amount_impact"])) == Decimal("150.00")
