"""M8 API-level smoke test: with no provider API key configured, the agent
endpoint must respond with a clear 'not configured' answer -- never a 500,
never a fabricated response.

The absence of a key is forced here rather than inherited from the
environment. Reading it from the developer's own backend/.env made this test
pass only for people who had not set one up yet, and turned it into a live
network call for everyone else.
"""
import pytest

from app.core.config import settings


@pytest.fixture()
def _no_provider_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "agent_provider", None)


def test_agent_query_without_api_key_is_honest_not_broken(api_client, _no_provider_key):
    resp = api_client.post("/api/v1/agent/query", json={"question": "What is Client A's match rate?"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["configured"] is False
    assert "not configured" in data["text"].lower()
    assert data["tool_calls"] == []


def test_agent_chat_without_api_key_is_honest_not_broken(api_client, _no_provider_key):
    resp = api_client.post(
        "/api/v1/agent/chat",
        json={"messages": [{"role": "user", "content": "run the reconciliations"}]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["configured"] is False
    assert "not configured" in data["text"].lower()
    # A turn that could not reach a provider must not claim anything is pending.
    assert data["awaiting_confirmation"] is None
    assert data["ui_hint"] is None
