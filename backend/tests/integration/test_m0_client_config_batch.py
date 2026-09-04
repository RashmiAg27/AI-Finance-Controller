"""M0 smoke test: create both clients, load+activate both real YAML configs,
create one empty batch each, and confirm the state machine rejects an
out-of-order transition."""
from pathlib import Path

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


def _load_yaml(client_code: str, version: str = "v1.yaml") -> str:
    return (CONFIGS_ROOT / client_code / version).read_text(encoding="utf-8")


def test_client_a_and_b_full_m0_flow(api_client):
    for code, name in [("client_a", "Client A Pvt Ltd"), ("client_b", "Client B Commerce Ltd")]:
        resp = api_client.post("/api/v1/clients", json={"code": code, "name": name})
        assert resp.status_code == 200, resp.text
        client_id = resp.json()["id"]

        raw_yaml = _load_yaml(code)
        resp = api_client.post(f"/api/v1/clients/{client_id}/config-versions", json={"raw_yaml": raw_yaml})
        assert resp.status_code == 200, resp.text
        config = resp.json()
        assert config["version"] == 1
        assert config["status"] == "DRAFT"

        resp = api_client.post(f"/api/v1/clients/{client_id}/config-versions/1/activate")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ACTIVE"

        resp = api_client.post(f"/api/v1/clients/{client_id}/batches", json={"batch_code": f"{code}-2026-09-01"})
        assert resp.status_code == 200, resp.text
        batch = resp.json()
        assert batch["status"] == "CREATED"
        assert batch["config_version_id"] == config["id"]


def test_batch_state_machine_rejects_out_of_order_transition(db_session):
    from app.core.errors import InvalidTransitionError
    from app.domains.batches import service, state_machine
    from app.domains.clients import config_loader, service as client_service

    client = client_service.create_client(db_session, code="client_state_test", name="State Test Client")
    raw_yaml = _load_yaml("client_a").replace("client_id: client_a", "client_id: client_state_test")
    config = config_loader.load_config_version(db_session, client_id=client.id, raw_yaml=raw_yaml)
    config_loader.activate_config_version(db_session, config_version_id=config.id)

    batch = service.create_batch(db_session, client_id=client.id, batch_code="b1")
    assert batch.status == state_machine.CREATED

    try:
        state_machine.transition(db_session, batch, state_machine.NORMALIZED)
        assert False, "expected InvalidTransitionError skipping straight to NORMALIZED"
    except InvalidTransitionError:
        pass

    state_machine.transition(db_session, batch, state_machine.FILES_RECEIVED)
    assert batch.status == state_machine.FILES_RECEIVED
    assert batch.files_received_at is not None

    try:
        state_machine.transition(db_session, batch, state_machine.CREATED)
        assert False, "expected InvalidTransitionError going backwards"
    except InvalidTransitionError:
        pass
