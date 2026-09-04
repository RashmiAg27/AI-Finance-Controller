"""M7 smoke test: cash position separates confirmed cash (from matched
external transactions) from expected inflows (open MISSING_EXTERNAL_RECORD
exceptions) and the honest unreconciled_amount figure; the forecast's
uncertainty band is sized directly by that same unreconciled_amount."""
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.synthetic import generator as gen
from app.synthetic import scenarios as sc

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def _tag(row: dict, eco_id: str) -> dict:
    return {**row, "_ground_truth_economic_id": eco_id}


def _missing_external_credit_scenario(amount: Decimal, base_date: date) -> sc.Scenario:
    eco_id = "CB-MISSEXT-0001"
    txn_date = base_date + timedelta(days=2)
    internal_row = _tag({
        "InternalRef": "INTREF-MISSEXT-0001", "OrderId": "",
        "PostedOn": txn_date.strftime("%Y-%m-%d"),
        "Amount": str(amount), "DrCr": "CR", "CustomerName": "PENDING CUSTOMER",
        "Notes": "Awaiting gateway settlement confirmation",
    }, eco_id)
    return sc.Scenario(
        scenario_name="MISSING_EXTERNAL_RECORD", economic_transaction_id=eco_id, client_code="client_b",
        rows_by_source={"internal_ledger": [internal_row]},
        expected_exception_type="MISSING_EXTERNAL_RECORD",
    )


def test_client_b_cash_position_and_forecast(api_client, tmp_path):
    base_date = date(2026, 9, 1)
    exact = sc.client_b_exact_match(1, base_date, random.Random(1))
    fee_adjusted = sc.client_b_fee_adjusted_settlement(1, base_date, random.Random(2))
    missing_amount = Decimal("15000.00")
    missing = _missing_external_credit_scenario(missing_amount, base_date)
    scenarios = [exact, fee_adjusted, missing]

    exact_gateway_credit = Decimal(exact.rows_by_source["payment_gateway"][0]["net_amount"])
    fee_gateway_credit = Decimal(fee_adjusted.rows_by_source["payment_gateway"][0]["net_amount"])
    expected_confirmed_cash = exact_gateway_credit + fee_gateway_credit

    resp = api_client.post("/api/v1/clients", json={"code": "client_b", "name": "Client B"})
    client_id = resp.json()["id"]
    api_client.post(f"/api/v1/clients/{client_id}/config-versions", json={"raw_yaml": _load_yaml("client_b")})
    api_client.post(f"/api/v1/clients/{client_id}/config-versions/1/activate")

    batch_code = "client_b-m7"
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

    position = api_client.get(f"/api/v1/clients/{client_id}/cash-position").json()
    assert Decimal(str(position["confirmed_cash"])) == expected_confirmed_cash
    assert Decimal(str(position["expected_inflows"])) == missing_amount
    assert Decimal(str(position["expected_outflows"])) == Decimal("0.00")
    assert Decimal(str(position["unreconciled_amount"])) == missing_amount

    forecast = api_client.get(f"/api/v1/clients/{client_id}/cash-forecast").json()
    expected_value = Decimal(str(position["confirmed_cash"])) + Decimal(str(position["expected_inflows"]))
    assert Decimal(str(forecast["expected_value"])) == expected_value
    assert Decimal(str(forecast["low_estimate"])) == expected_value - missing_amount
    assert Decimal(str(forecast["high_estimate"])) == expected_value + missing_amount
    assert forecast["horizon_days"] == 7
    assert "prototype" in forecast["assumptions_note"].lower()
