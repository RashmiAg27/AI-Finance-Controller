"""M2 smoke test: run Passes 1-4 against a fixture with known exact,
normalized-partial, timing-difference, and amount/counterparty-tolerance
scenarios, and assert each resolves via the expected pass with recorded
evidence."""
import random
from datetime import date
from pathlib import Path

from app.synthetic import generator as gen
from app.synthetic import scenarios as sc

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def test_client_a_deterministic_passes_1_to_4(api_client, tmp_path):
    base_date = date(2026, 9, 1)
    scenarios = [
        sc.client_a_exact_match(1, base_date, random.Random(1)),
        sc.client_a_exact_match(2, base_date, random.Random(2)),
        sc.client_a_normalized_reference_match(1, base_date, random.Random(3)),
        sc.client_a_timing_difference(1, base_date, random.Random(4)),
        sc.client_a_counterparty_variation(1, base_date, random.Random(5)),
    ]
    expected_match_type_by_scenario = {
        "EXACT_IDENTIFIER_MATCH": "EXACT_REFERENCE",
        "NORMALIZED_REFERENCE_MATCH": "NORMALIZED_REFERENCE",
        "TIMING_DIFFERENCE": "AMOUNT_DATE",
        "COUNTERPARTY_VARIATION": "AMOUNT_COUNTERPARTY_DATE_INSTRUMENT",
    }
    scenario_by_eco_id = {s.economic_transaction_id: s for s in scenarios}

    resp = api_client.post("/api/v1/clients", json={"code": "client_a", "name": "Client A"})
    client_id = resp.json()["id"]
    api_client.post(f"/api/v1/clients/{client_id}/config-versions", json={"raw_yaml": _load_yaml("client_a")})
    api_client.post(f"/api/v1/clients/{client_id}/config-versions/1/activate")

    batch_code = "client_a-m2"
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
    batch = resp.json()
    assert batch["status"] == "CLOSED", batch
    assert batch["reconciliation_completed_at"] is not None

    runs = api_client.get(f"/api/v1/batches/{batch_id}/reconciliation-runs").json()
    assert len(runs) == 1
    stats = runs[0]["stats_json"]
    assert stats["total_matches"] == len(scenarios)
    assert stats["unmatched_internal"] == 0
    assert stats["unmatched_external"] == 0

    txns = api_client.get(f"/api/v1/batches/{batch_id}/transactions").json()
    eco_id_by_txn_id = {t["id"]: t["metadata_json"].get("economic_transaction_id") for t in txns}

    matches = api_client.get(f"/api/v1/batches/{batch_id}/matches").json()
    assert len(matches) == len(scenarios)

    seen_scenarios = set()
    for match in matches:
        assert match["cardinality"] == "ONE_TO_ONE"
        assert match["status"] == "CONFIRMED"
        assert match["evidence"], "every match must carry structured evidence, never a bare boolean"

        txn_ids_in_match = {t["transaction_id"] for t in match["transactions"]}
        eco_ids = {eco_id_by_txn_id[tid] for tid in txn_ids_in_match}
        assert len(eco_ids) == 1, f"match {match['id']} mixes transactions from different economic events: {eco_ids}"
        eco_id = eco_ids.pop()
        scenario = scenario_by_eco_id[eco_id]
        seen_scenarios.add(scenario.scenario_name)

        expected_type = expected_match_type_by_scenario[scenario.scenario_name]
        assert match["match_type"] == expected_type, (
            f"scenario {scenario.scenario_name} ({eco_id}) matched via {match['match_type']}, "
            f"expected {expected_type}"
        )

    assert seen_scenarios == set(expected_match_type_by_scenario)
