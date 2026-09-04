"""GeminiProvider does two-way translation between the controller's
Anthropic-shaped message/tool format and the google-genai SDK's
contents/function-call types.

These are pure, offline translation functions -- constructing a genai.Client
does not make a network call -- so this runs without a real GEMINI_API_KEY.
"""
from types import SimpleNamespace

from google.genai import types

from app.agent.provider import GeminiProvider, ToolUseBlock


def _make_provider() -> GeminiProvider:
    return GeminiProvider(api_key="dummy-key-for-offline-translation-test", model="gemini-3.6-flash")


def test_translate_tools_to_gemini_function_declarations():
    provider = _make_provider()
    tools = [
        {"name": "get_clients", "description": "List clients.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_batch_status", "description": "Get batch status.",
         "input_schema": {"type": "object", "properties": {"batch_id": {"type": "string"}},
                          "required": ["batch_id"]}},
    ]
    translated = provider._translate_tools(tools)
    assert len(translated) == 1
    declarations = translated[0].function_declarations
    assert declarations[0].name == "get_clients"
    assert declarations[1].parameters.required == ["batch_id"]


def test_translate_tools_empty_yields_no_tool_block():
    """An empty tool list must not become a Tool with zero declarations --
    the API rejects that."""
    assert _make_provider()._translate_tools([]) == []


def test_translate_messages_initial_question_becomes_user_text_part():
    provider = _make_provider()
    contents = provider._translate_messages(
        [{"role": "user", "content": "What is Meridian's match rate?"}]
    )
    assert len(contents) == 1
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "What is Meridian's match rate?"


def test_translate_messages_round_trips_tool_use_and_tool_result():
    provider = _make_provider()
    messages = [
        {"role": "user", "content": "List the clients."},
        {"role": "assistant", "content": [ToolUseBlock(id="call_1", name="get_clients", input={})]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call_1", "name": "get_clients",
             "content": '{"clients": []}'},
        ]},
    ]
    contents = provider._translate_messages(messages)

    assert contents[1].role == "model"
    assert contents[1].parts[0].function_call.name == "get_clients"

    assert contents[2].role == "user"
    response_part = contents[2].parts[0].function_response
    assert response_part.name == "get_clients"
    assert response_part.response["result"] == {"clients": []}


def test_translate_messages_echoes_thought_signature_back():
    """Gemini 3.x rejects the next request with a 400 if the signature it
    attached to a function call is not returned on that same call. Losing it
    here is what breaks the whole tool-calling loop, so it is asserted."""
    provider = _make_provider()
    signature = b"opaque-signature-bytes"
    contents = provider._translate_messages([
        {"role": "assistant", "content": [
            ToolUseBlock(id="call_1", name="get_clients", input={}, thought_signature=signature),
        ]},
    ])
    assert contents[0].parts[0].thought_signature == signature


def test_translate_response_captures_thought_signature():
    provider = _make_provider()
    signature = b"sig"
    part = SimpleNamespace(text=None, thought=False, thought_signature=signature,
                           function_call=SimpleNamespace(name="get_clients", args={}))
    response = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]), finish_reason="STOP")]
    )
    normalized = provider._translate_response(response)
    assert normalized.content[0].thought_signature == signature


def test_translate_response_text_only_is_end_turn():
    provider = _make_provider()
    part = SimpleNamespace(text="There is one client.", function_call=None, thought=False,
                           thought_signature=None)
    response = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]), finish_reason="STOP")]
    )
    normalized = provider._translate_response(response)
    assert normalized.stop_reason == "end_turn"
    assert normalized.content[0].type == "text"
    assert normalized.content[0].text == "There is one client."


def test_translate_response_function_call_is_tool_use():
    provider = _make_provider()
    part = SimpleNamespace(text=None, thought=False, thought_signature=None,
                           function_call=SimpleNamespace(name="get_clients", args={}))
    response = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]), finish_reason="STOP")]
    )
    normalized = provider._translate_response(response)
    assert normalized.stop_reason == "tool_use"
    assert normalized.content[0].type == "tool_use"
    assert normalized.content[0].name == "get_clients"
    assert normalized.content[0].id


def test_translate_response_skips_reasoning_parts():
    """A thought part is the model's internal reasoning, not an answer."""
    provider = _make_provider()
    thought = SimpleNamespace(text="let me think", thought=True, thought_signature=None,
                              function_call=None)
    answer = SimpleNamespace(text="Two clients.", thought=False, thought_signature=None,
                             function_call=None)
    response = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[thought, answer]),
                                    finish_reason="STOP")]
    )
    normalized = provider._translate_response(response)
    assert len(normalized.content) == 1
    assert normalized.content[0].text == "Two clients."


def test_empty_candidate_reports_why_instead_of_silence():
    """A thinking model that spends its whole budget reasoning returns zero
    parts. Rendering that as an empty answer would look like the agent
    ignoring the question."""
    provider = _make_provider()
    response = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]),
                                    finish_reason="MAX_TOKENS")],
        usage_metadata=SimpleNamespace(total_token_count=70),
    )
    normalized = provider._translate_response(response)
    assert normalized.stop_reason == "end_turn"
    assert "MAX_TOKENS" in normalized.content[0].text
