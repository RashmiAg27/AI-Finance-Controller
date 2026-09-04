"""M5a smoke test: whatever the deterministic engine (Passes 1-6) cannot
resolve lands in the exception queue with a specific taxonomy value and
recorded evidence -- never silently dropped."""
import random
from datetime import date
from pathlib import Path

from app.synthetic import generator as gen
from app.synthetic import scenarios as sc

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str) -> str:
    return (CONFIGS_ROOT / client_code / "v1.yaml").read_text(encoding="utf-8")


def test_client_a_unresolved_scenarios_become_exceptions(api_client, tmp_path):
    base_date = date(2026, 9, 1)
    scenarios = [
        sc.client_a_exact_match(1, base_date, random.Random(1)),  # control: should NOT become an exception
        sc.client_a_missing_external_record(1, base_date, random.Random(2)),
        sc.client_a_duplicate_posting(1, base_date, random.Random(3)),
    ]

    resp = api_client.post("/api/v1/clients", json={"code": "client_a", "name": "Client A"})
    client_id = resp.json()["id"]
    api_client.post(f"/api/v1/clients/{client_id}/config-versions", json={"raw_yaml": _load_yaml("client_a")})
    api_client.post(f"/api/v1/clients/{client_id}/config-versions/1/activate")

    batch_code = "client_a-m5a"
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
    # pipeline continues past exceptions into settlement processing regardless
    # of whether every exception is resolved -- EXCEPTIONS_RESOLVED is optional
    assert batch["status"] == "CLOSED", batch
    assert batch["exceptions_identified_at"] is not None

    exceptions = api_client.get(f"/api/v1/batches/{batch_id}/exceptions").json()
    types = sorted(e["exception_type"] for e in exceptions)
    assert types == ["DUPLICATE", "DUPLICATE", "MISSING_EXTERNAL_RECORD"]

    for exc in exceptions:
        assert exc["status"] == "OPEN"
        assert exc["likely_cause"]
        assert exc["recommended_action"]
        assert exc["evidence"], "every exception must carry evidence, never a bare classification"

    duplicate_excs = [e for e in exceptions if e["exception_type"] == "DUPLICATE"]
    for exc in duplicate_excs:
        related = [t for t in exc["transactions"] if t["role"] == "RELATED"]
        assert len(related) == 1

    # the exact-match control transaction must not appear anywhere in the exception queue
    txns = api_client.get(f"/api/v1/batches/{batch_id}/transactions").json()
    exact_match_txn_ids = {
        t["id"] for t in txns
        if t["metadata_json"].get("economic_transaction_id", "").startswith("CA-EXACT-")
    }
    exception_txn_ids = {t["transaction_id"] for e in exceptions for t in e["transactions"]}
    assert not (exact_match_txn_ids & exception_txn_ids)
