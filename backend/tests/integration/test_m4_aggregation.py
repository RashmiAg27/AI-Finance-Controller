"""M4 smoke test: a 1:N split settlement (Client A) and an N:1 bundled
settlement (Client B) each resolve via Pass 6 aggregation, with the correct
cardinality and every contributing transaction linked."""
import random
from datetime import date
from pathlib import Path

from app.synthetic import generator as gen
from app.synthetic import scenarios as sc

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def _run_batch(api_client, tmp_path, client_code: str, batch_code: str, scenarios):
    resp = api_client.post("/api/v1/clients", json={"code": client_code, "name": client_code})
    client_id = resp.json()["id"]
    api_client.post(f"/api/v1/clients/{client_id}/config-versions", json={"raw_yaml": _load_yaml(client_code)})
    api_client.post(f"/api/v1/clients/{client_id}/config-versions/1/activate")

    resp = api_client.post(f"/api/v1/clients/{client_id}/batches", json={"batch_code": batch_code})
    batch_id = resp.json()["id"]

    written = gen.generate_batch_files(scenarios, client_code, batch_code, tmp_path)
    for source_id, path in written.items():
        with path.open("rb") as f:
            resp = api_client.post(
                f"/api/v1/batches/{batch_id}/files", params={"source_id": source_id}, files={"file": (path.name, f)}
            )
            assert resp.status_code == 200, resp.text

    api_client.post(f"/api/v1/batches/{batch_id}/files/complete")
    resp = api_client.post(f"/api/v1/batches/{batch_id}/process")
    assert resp.status_code == 200, resp.text
    return batch_id, resp.json()


def test_client_a_one_to_many_split_settlement(api_client, tmp_path):
    scenarios = [sc.client_a_split_settlement_one_to_many(1, date(2026, 9, 1), random.Random(1))]
    batch_id, batch = _run_batch(api_client, tmp_path, "client_a", "client_a-m4", scenarios)
    assert batch["status"] == "CLOSED"

    runs = api_client.get(f"/api/v1/batches/{batch_id}/reconciliation-runs").json()
    stats = runs[0]["stats_json"]
    assert stats["matches_by_pass"].get("6") == 1
    assert stats["unmatched_internal"] == 0
    assert stats["unmatched_external"] == 0

    matches = api_client.get(f"/api/v1/batches/{batch_id}/matches").json()
    aggregated = [m for m in matches if m["match_type"] == "AGGREGATED"]
    assert len(aggregated) == 1
    match = aggregated[0]
    assert match["cardinality"] == "ONE_TO_MANY"

    sides = {"SOURCE": 0, "TARGET": 0}
    for t in match["transactions"]:
        sides[t["side"]] += 1
    assert sides == {"SOURCE": 1, "TARGET": 2}

    evidence_types = {e["evidence_type"] for e in match["evidence"]}
    assert {"AGGREGATION_KEY", "AMOUNT_COMPARISON", "DATE_COMPARISON"} <= evidence_types


def test_client_b_many_to_one_bundled_settlement(api_client, tmp_path):
    scenarios = [sc.client_b_bundled_settlement_many_to_one(1, date(2026, 9, 1), random.Random(2))]
    batch_id, batch = _run_batch(api_client, tmp_path, "client_b", "client_b-m4", scenarios)
    assert batch["status"] == "CLOSED"

    runs = api_client.get(f"/api/v1/batches/{batch_id}/reconciliation-runs").json()
    stats = runs[0]["stats_json"]
    assert stats["matches_by_pass"].get("6") == 1
    assert stats["unmatched_internal"] == 0
    assert stats["unmatched_external"] == 0

    matches = api_client.get(f"/api/v1/batches/{batch_id}/matches").json()
    aggregated = [m for m in matches if m["match_type"] == "AGGREGATED"]
    assert len(aggregated) == 1
    match = aggregated[0]
    assert match["cardinality"] == "MANY_TO_ONE"

    sides = {"SOURCE": 0, "TARGET": 0}
    for t in match["transactions"]:
        sides[t["side"]] += 1
    assert sides == {"SOURCE": 3, "TARGET": 1}
