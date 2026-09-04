"""A failing LLM provider must degrade honestly, never into a 500 the panel
renders as a blank turn and never into a fabricated answer.

Rate limiting is the case that actually bites in practice -- free-tier Gemini
keys cap daily requests -- so it gets its own assertion.
"""
import pytest

from app.agent.controller import converse
from app.agent.provider import LLMProvider


class _FailingProvider(LLMProvider):
    def __init__(self, exc: Exception):
        self._exc = exc

    def create_message(self, *, system, messages, tools, max_tokens=4096):
        raise self._exc


def _ask(db_session, exc: Exception):
    return converse(db_session, [{"role": "user", "content": "how did the reconciliation go?"}],
                    provider=_FailingProvider(exc))


def test_rate_limit_is_explained_not_raised(db_session):
    answer = _ask(db_session, RuntimeError(
        "429 RESOURCE_EXHAUSTED. Quota exceeded for metric generate_content_free_tier_requests"
    ))
    assert "quota" in answer.text.lower()
    assert "nothing was run" in answer.text.lower()
    # The turn failed, so it must not leave the panel believing an action is pending.
    assert answer.awaiting_confirmation is None


def test_bad_api_key_is_explained(db_session):
    answer = _ask(db_session, RuntimeError("401 PERMISSION_DENIED: API key not valid"))
    assert "api key" in answer.text.lower()


def test_missing_model_is_explained(db_session, monkeypatch):
    """The env var named in the message must match whichever provider is
    actually active -- forced here so the assertion doesn't depend on
    whatever happens to be set in the developer's own backend/.env."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "agent_provider", "gemini")
    answer = _ask(db_session, RuntimeError(
        "404 This model models/gemini-2.5-flash is no longer available to new users"
    ))
    assert "GEMINI_MODEL" in answer.text


def test_missing_model_names_whichever_provider_is_actually_active(db_session, monkeypatch):
    """The bug this guards against: the message used to hardcode GEMINI_MODEL
    regardless of which provider actually failed, so a Groq or OpenAI user
    was told to edit a setting that didn't exist for their provider."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "agent_provider", "groq")
    answer = _ask(db_session, RuntimeError("404 model `some-decommissioned-model` does not exist"))
    assert "GROQ_MODEL" in answer.text
    assert "GEMINI_MODEL" not in answer.text


def test_unknown_failure_still_reports_the_provider_message(db_session):
    answer = _ask(db_session, ValueError("something specific went wrong upstream"))
    assert "something specific went wrong upstream" in answer.text
    assert "nothing was run" in answer.text.lower()


@pytest.mark.parametrize("exc", [
    RuntimeError("429 RESOURCE_EXHAUSTED"),
    RuntimeError("boom"),
])
def test_failure_never_claims_success(db_session, exc):
    answer = _ask(db_session, exc)
    assert answer.text
    # No invented reconciliation figures.
    assert "match rate" not in answer.text.lower()
