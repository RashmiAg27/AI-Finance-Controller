"""LLM provider abstraction. The controller and tool-calling loop
(app.agent.controller) only ever see one normalized shape for a response --
`.stop_reason` ("tool_use" | "end_turn") and `.content`, a list of blocks
each with `.type` ("text" | "tool_use") plus `.text` or `.id`/`.name`/
`.input` -- which happens to be the Anthropic SDK's own shape. Anthropic
therefore needs no translation; GeminiProvider translates both directions
(TOOL_SCHEMAS + message history -> Gemini's contents/function-call format,
and Gemini's response -> the normalized shape) so the controller loop stays
provider-agnostic. Get a genuinely different vendor by giving it the same
create_message() contract, whichever direction the translation runs.
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings


class AgentNotConfiguredError(Exception):
    pass


# Gemini 3.x and Claude both spend output tokens on reasoning before emitting
# anything visible. A budget sized for the answer alone gets consumed by that
# and returns an empty candidate, so the default is set well above what a
# side-panel reply needs.
DEFAULT_MAX_TOKENS = 4096


class LLMProvider(ABC):
    @abstractmethod
    def create_message(self, *, system: str, messages: list[dict], tools: list[dict],
                       max_tokens: int = DEFAULT_MAX_TOKENS):
        ...


class NotConfiguredProvider(LLMProvider):
    """Returned when no provider API key is set -- the agent must fail with
    a clear, honest message rather than crash or silently do nothing."""

    def create_message(self, *, system: str, messages: list[dict], tools: list[dict],
                       max_tokens: int = DEFAULT_MAX_TOKENS):
        raise AgentNotConfiguredError(
            "The AI Finance Controller agent is not configured: no GEMINI_API_KEY, ANTHROPIC_API_KEY "
            "or OPENAI_API_KEY is set. Set one in backend/.env (see .env.example) and restart the "
            "API to enable the agent."
        )


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def create_message(self, *, system: str, messages: list[dict], tools: list[dict],
                       max_tokens: int = DEFAULT_MAX_TOKENS):
        return self._client.messages.create(
            model=self._model, max_tokens=max_tokens, system=system, messages=messages, tools=tools,
        )


# ---------------------------------------------------------------------------
# Normalized response shape (what every provider must return from
# create_message, regardless of the underlying SDK) -- plain dataclasses
# rather than a Protocol so GeminiProvider can construct them directly.
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"
    # Gemini 3.x returns an opaque signature on the part that produced a
    # function call, and REJECTS the next request if that signature is not
    # echoed back with the call in the history (400 "Function call is missing
    # a thought_signature"). It is meaningless to us and must simply survive
    # the round trip, so it rides along on the normalized block.
    thought_signature: bytes | None = None


@dataclass
class NormalizedResponse:
    stop_reason: str
    content: list = field(default_factory=list)


class GeminiProvider(LLMProvider):
    """Gemini via the current `google-genai` SDK.

    Migrated off `google-generativeai` because that package is sunset AND
    structurally cannot talk to Gemini 3.x with tools: its Part message has no
    `thought_signature` field, so the signature the model requires to be echoed
    back on a function call cannot survive a round trip through it.
    """

    def __init__(self, api_key: str, model: str):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        self._call_counter = 0

    def create_message(self, *, system: str, messages: list[dict], tools: list[dict],
                       max_tokens: int = DEFAULT_MAX_TOKENS):
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            tools=self._translate_tools(tools) or None,
            # Deterministic behaviour matters here: the controller loops over
            # tool calls, and a wandering model burns the iteration budget.
            temperature=0.0,
        )
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=self._translate_messages(messages),
            config=config,
        )
        return self._translate_response(response)

    @staticmethod
    def _translate_tools(tools: list[dict]) -> list:
        from google.genai import types

        if not tools:
            return []
        return [types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=t["name"], description=t["description"], parameters=t["input_schema"],
            )
            for t in tools
        ])]

    def _translate_messages(self, messages: list[dict]) -> list:
        from google.genai import types

        contents = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            content = msg["content"]

            if isinstance(content, str):
                contents.append(types.Content(role=role, parts=[types.Part(text=content)]))
                continue

            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    parts.append(types.Part(function_response=types.FunctionResponse(
                        name=block.get("name", "unknown_tool"),
                        response={"result": json.loads(block["content"])},
                    )))
                elif isinstance(block, dict) and "text" in block:
                    parts.append(types.Part(text=block["text"]))
                elif getattr(block, "type", None) == "text":
                    parts.append(types.Part(text=block.text))
                elif getattr(block, "type", None) == "tool_use":
                    # The signature must go back exactly as it came, on the
                    # same part as the call it belongs to.
                    parts.append(types.Part(
                        function_call=types.FunctionCall(name=block.name, args=block.input),
                        thought_signature=getattr(block, "thought_signature", None),
                    ))
            contents.append(types.Content(role=role, parts=parts))
        return contents

    def _translate_response(self, response: Any) -> NormalizedResponse:
        candidate = response.candidates[0]
        blocks: list = []
        has_tool_use = False
        for part in (candidate.content.parts or []):
            # Reasoning parts are internal to the model and are not an answer.
            if getattr(part, "thought", False):
                continue
            function_call = getattr(part, "function_call", None)
            if function_call and getattr(function_call, "name", None):
                self._call_counter += 1
                blocks.append(ToolUseBlock(
                    id=f"call_{self._call_counter}",
                    name=function_call.name,
                    input=dict(function_call.args or {}),
                    thought_signature=getattr(part, "thought_signature", None),
                ))
                has_tool_use = True
            elif getattr(part, "text", None):
                blocks.append(TextBlock(text=part.text))

        if not blocks:
            # A thinking model that exhausts its output budget before emitting
            # anything returns a candidate with zero parts. Saying so beats
            # returning an empty answer the caller would render as silence.
            blocks.append(TextBlock(text=self._empty_candidate_message(candidate, response)))

        return NormalizedResponse(stop_reason="tool_use" if has_tool_use else "end_turn", content=blocks)

    @staticmethod
    def _empty_candidate_message(candidate: Any, response: Any) -> str:
        finish = getattr(candidate, "finish_reason", None)
        finish_name = getattr(finish, "name", str(finish))
        if finish_name in ("2", "MAX_TOKENS", "FinishReason.MAX_TOKENS"):
            usage = getattr(response, "usage_metadata", None)
            used = getattr(usage, "total_token_count", "?") if usage else "?"
            return (
                "The model used its entire output budget on reasoning and produced no answer "
                f"(finish_reason=MAX_TOKENS, {used} tokens). Raise the token budget or ask a "
                "narrower question."
            )
        if finish_name in ("3", "SAFETY", "4", "RECITATION",
                            "FinishReason.SAFETY", "FinishReason.RECITATION"):
            return f"The model declined to answer (finish_reason={finish_name})."
        return f"The model returned an empty response (finish_reason={finish_name})."


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible chat completions -- also serves Groq, which speaks
    the same API, via a different base_url (see get_provider()).

    The most involved of the translations, because this API models the
    conversation differently in two ways the loop cares about:

      * the system prompt is a message in the list, not a separate argument;
      * a tool result is its own message with `role: "tool"`, keyed back to
        the call by `tool_call_id` -- so the id issued must be kept and
        returned verbatim, exactly as Gemini's thought_signature must be.

    Arguments arrive as a JSON *string* rather than an object, so they are
    parsed on the way in and re-serialised on the way back out.
    """

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        import openai

        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def create_message(self, *, system: str, messages: list[dict], tools: list[dict],
                       max_tokens: int = DEFAULT_MAX_TOKENS):
        request: dict[str, Any] = {
            "model": self._model,
            "messages": self._translate_messages(system, messages),
            "max_completion_tokens": max_tokens,
        }
        translated_tools = self._translate_tools(tools)
        if translated_tools:
            request["tools"] = translated_tools
        response = self._client.chat.completions.create(**request)
        return self._translate_response(response)

    @staticmethod
    def _translate_tools(tools: list[dict]) -> list[dict]:
        return [
            {"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["input_schema"],
            }}
            for t in tools
        ]

    @staticmethod
    def _translate_messages(system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]

        for msg in messages:
            content = msg["content"]

            if isinstance(content, str):
                out.append({"role": msg["role"], "content": content})
                continue

            if msg["role"] == "assistant":
                text_parts, tool_calls = [], []
                for block in content:
                    if getattr(block, "type", None) == "text":
                        text_parts.append(block.text)
                    elif isinstance(block, dict) and "text" in block:
                        text_parts.append(block["text"])
                    elif getattr(block, "type", None) == "tool_use":
                        tool_calls.append({
                            "id": block.id, "type": "function",
                            "function": {"name": block.name, "arguments": json.dumps(block.input)},
                        })
                assistant: dict[str, Any] = {"role": "assistant",
                                             "content": "".join(text_parts) or None}
                if tool_calls:
                    assistant["tool_calls"] = tool_calls
                out.append(assistant)
                continue

            # A user turn carrying tool results becomes one `tool` message per
            # result -- OpenAI has no notion of several results in one turn.
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    out.append({
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": block["content"],
                    })
                elif isinstance(block, dict) and "text" in block:
                    out.append({"role": "user", "content": block["text"]})
        return out

    def _translate_response(self, response: Any) -> NormalizedResponse:
        choice = response.choices[0]
        message = choice.message
        blocks: list = []

        if getattr(message, "content", None):
            blocks.append(TextBlock(text=message.content))

        for call in (getattr(message, "tool_calls", None) or []):
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                # A model that emits malformed JSON arguments must surface as a
                # tool error the loop can report, not as a crashed turn.
                arguments = {"__malformed_arguments__": call.function.arguments}
            blocks.append(ToolUseBlock(id=call.id, name=call.function.name, input=arguments))

        has_tool_use = any(getattr(b, "type", None) == "tool_use" for b in blocks)

        if not blocks:
            finish = getattr(choice, "finish_reason", None)
            if finish == "length":
                blocks.append(TextBlock(text=(
                    "The model used its entire output budget before producing an answer "
                    "(finish_reason=length). Raise the token budget or ask a narrower question."
                )))
            elif finish == "content_filter":
                blocks.append(TextBlock(text="The model declined to answer (content filter)."))
            else:
                blocks.append(TextBlock(text=f"The model returned an empty response (finish_reason={finish})."))

        return NormalizedResponse(stop_reason="tool_use" if has_tool_use else "end_turn", content=blocks)


# The env var names for each provider, used both to build a client and to
# name the right variable in an error message -- see resolve_provider_name()
# and app.agent.controller._provider_failure_message.
PROVIDER_ENV_VARS = {
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL"),
    "groq": ("GROQ_API_KEY", "GROQ_MODEL"),
}


def _provider_keys() -> dict[str, str | None]:
    return {
        "gemini": settings.gemini_api_key,
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "groq": settings.groq_api_key,
    }


def resolve_provider_name() -> str | None:
    """Which provider get_provider() would pick, without constructing a
    client -- lets an error message name the actual provider/env vars
    involved instead of assuming it was always the first one in the list."""
    forced = (settings.agent_provider or "").strip().lower()
    if forced:
        return forced if forced in PROVIDER_ENV_VARS else None
    keys = _provider_keys()
    for name in ("gemini", "anthropic", "openai", "groq"):
        if keys[name]:
            return name
    return None


def get_provider() -> LLMProvider:
    """Picks the provider to use.

    AGENT_PROVIDER forces one explicitly; otherwise the first key present
    wins, in the order below. Forcing a provider whose key is missing is an
    error rather than a silent fallback -- quietly answering from a different
    vendor than the one asked for would be worse than failing.
    """
    forced = (settings.agent_provider or "").strip().lower()

    builders = {
        "gemini": lambda: GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model),
        "anthropic": lambda: AnthropicProvider(api_key=settings.anthropic_api_key,
                                               model=settings.anthropic_model),
        "openai": lambda: OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model),
        "groq": lambda: OpenAIProvider(api_key=settings.groq_api_key, model=settings.groq_model,
                                       base_url="https://api.groq.com/openai/v1"),
    }
    keys = _provider_keys()

    if forced:
        if forced not in builders:
            raise AgentNotConfiguredError(
                f"AGENT_PROVIDER={forced!r} is not recognised; expected one of {sorted(builders)}."
            )
        if not keys[forced]:
            raise AgentNotConfiguredError(
                f"AGENT_PROVIDER is set to {forced!r} but {forced.upper()}_API_KEY is empty. "
                "Set the key in backend/.env and restart the API."
            )
        return builders[forced]()

    for name in ("gemini", "anthropic", "openai", "groq"):
        if keys[name]:
            return builders[name]()
    return NotConfiguredProvider()
