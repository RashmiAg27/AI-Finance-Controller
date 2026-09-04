"""OpenAIProvider translates between the controller's Anthropic-shaped
messages and OpenAI chat completions.

Two things differ structurally from the other providers and are what these
tests guard: the system prompt is a message rather than an argument, and a
tool result is its own `role: "tool"` message keyed by `tool_call_id`. Losing
that id breaks the loop the same way losing Gemini's thought_signature does.

Constructing an openai.OpenAI client makes no network call, so this runs
offline without a real key.
"""
from types import SimpleNamespace

import pytest

from app.agent.provider import (
    AgentNotConfiguredError,
    NotConfiguredProvider,
    OpenAIProvider,
    ToolUseBlock,
    get_provider,
)


def _make_provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="sk-dummy-offline-translation-test", model="gpt-5")


def _message(content=None, tool_calls=None, finish_reason="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=tool_calls),
            finish_reason=finish_reason,
        )]
    )


def _call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def test_translate_tools_wraps_schema_in_function_envelope():
    translated = _make_provider()._translate_tools([
        {"name": "get_clients", "description": "List clients.",
         "input_schema": {"type": "object", "properties": {}}},
    ])
    assert translated[0]["type"] == "function"
    assert translated[0]["function"]["name"] == "get_clients"
    assert translated[0]["function"]["parameters"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def test_system_prompt_becomes_the_first_message():
    out = _make_provider()._translate_messages("You are the controller.", [
        {"role": "user", "content": "hello"},
    ])
    assert out[0] == {"role": "system", "content": "You are the controller."}
    assert out[1] == {"role": "user", "content": "hello"}


def test_tool_call_arguments_are_serialised_to_a_json_string():
    out = _make_provider()._translate_messages("sys", [
        {"role": "assistant", "content": [
            ToolUseBlock(id="call_abc", name="get_batch_report", input={"batch_id": "b1"}),
        ]},
    ])
    call = out[1]["tool_calls"][0]
    assert call["id"] == "call_abc"
    assert call["function"]["name"] == "get_batch_report"
    # OpenAI takes arguments as a JSON string, not an object.
    assert call["function"]["arguments"] == '{"batch_id": "b1"}'


def test_tool_results_become_tool_role_messages_keyed_by_call_id():
    out = _make_provider()._translate_messages("sys", [
        {"role": "user", "content": "how did it go?"},
        {"role": "assistant", "content": [
            ToolUseBlock(id="call_1", name="get_clients", input={}),
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call_1", "name": "get_clients",
             "content": '{"clients": []}'},
        ]},
    ])
    result = out[-1]
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "call_1"
    assert result["content"] == '{"clients": []}'


def test_several_tool_results_become_several_tool_messages():
    """OpenAI has no notion of several results in one turn, so a fan-out turn
    must be split rather than concatenated."""
    out = _make_provider()._translate_messages("sys", [
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call_1", "name": "a", "content": "{}"},
            {"type": "tool_result", "tool_use_id": "call_2", "name": "b", "content": "{}"},
        ]},
    ])
    tool_messages = [m for m in out if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["call_1", "call_2"]


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

def test_text_response_is_end_turn():
    normalized = _make_provider()._translate_response(_message(content="Two clients."))
    assert normalized.stop_reason == "end_turn"
    assert normalized.content[0].text == "Two clients."


def test_tool_call_response_preserves_openai_call_id():
    """The id must survive verbatim -- the next request keys the result to it."""
    normalized = _make_provider()._translate_response(
        _message(tool_calls=[_call("call_xyz", "get_clients", "{}")])
    )
    assert normalized.stop_reason == "tool_use"
    assert normalized.content[0].id == "call_xyz"
    assert normalized.content[0].name == "get_clients"
    assert normalized.content[0].input == {}


def test_malformed_tool_arguments_do_not_crash_the_turn():
    normalized = _make_provider()._translate_response(
        _message(tool_calls=[_call("call_1", "get_clients", "{not json")])
    )
    assert normalized.stop_reason == "tool_use"
    assert "__malformed_arguments__" in normalized.content[0].input


def test_truncated_response_explains_itself():
    normalized = _make_provider()._translate_response(_message(finish_reason="length"))
    assert "budget" in normalized.content[0].text.lower()


def test_content_filter_is_reported_honestly():
    normalized = _make_provider()._translate_response(_message(finish_reason="content_filter"))
    assert "declined" in normalized.content[0].text.lower()


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def test_openai_key_alone_selects_openai(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "agent_provider", None)
    assert isinstance(get_provider(), OpenAIProvider)


def test_agent_provider_forces_choice_over_key_order(monkeypatch):
    """With several keys present, the explicit setting decides -- otherwise
    adding a key would silently change which vendor answers."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "gem-key")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "agent_provider", "openai")
    assert isinstance(get_provider(), OpenAIProvider)


def test_forcing_a_provider_without_its_key_is_an_error_not_a_fallback(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "gem-key")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "agent_provider", "openai")
    with pytest.raises(AgentNotConfiguredError, match="OPENAI_API_KEY"):
        get_provider()


def test_no_keys_at_all_is_still_the_not_configured_provider(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "agent_provider", None)
    assert isinstance(get_provider(), NotConfiguredProvider)
