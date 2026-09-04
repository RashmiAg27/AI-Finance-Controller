"""Controller-loop tests using a mock LLMProvider (shaped like the Anthropic
SDK's response objects) so the tool-calling mechanics -- message threading,
tool execution, evidence trace, and the not-configured path -- are verified
without needing a real API key or network access."""
from dataclasses import dataclass, field

from app.agent.controller import answer_question
from app.agent.provider import AgentNotConfiguredError, LLMProvider
from app.domains.clients import config_loader
from app.domains.clients import service as client_service
from pathlib import Path

CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs" / "clients"


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class FakeResponse:
    stop_reason: str
    content: list = field(default_factory=list)


class ScriptedProvider(LLMProvider):
    """Returns a pre-scripted sequence of responses, one per call, so a test
    can assert exactly how the controller drives a tool-use turn."""

    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create_message(self, *, system, messages, tools, max_tokens=1024):
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": tools})
        return self._responses.pop(0)


def _seed_one_client(db_session):
    client = client_service.create_client(db_session, code="client_a", name="Client A")
    raw_yaml = (CONFIGS_ROOT / "client_a" / "v1.yaml").read_text(encoding="utf-8")
    config = config_loader.load_config_version(db_session, client_id=client.id, raw_yaml=raw_yaml)
    config_loader.activate_config_version(db_session, config_version_id=config.id)
    db_session.commit()
    return client


def test_not_configured_provider_returns_honest_message(db_session):
    from app.agent.provider import NotConfiguredProvider

    answer = answer_question(db_session, "What is Client A's match rate?", provider=NotConfiguredProvider())
    assert answer.configured is False
    assert "not configured" in answer.text.lower()
    assert answer.tool_calls == []


def test_tool_use_loop_executes_tool_and_returns_final_text(db_session):
    client = _seed_one_client(db_session)

    provider = ScriptedProvider([
        FakeResponse(stop_reason="tool_use", content=[
            FakeToolUseBlock(id="tu_1", name="get_clients", input={}),
        ]),
        FakeResponse(stop_reason="end_turn", content=[
            FakeTextBlock(text=f"There is one client: {client.code}."),
        ]),
    ])

    answer = answer_question(db_session, "List the clients.", provider=provider)

    assert answer.configured is True
    assert client.code in answer.text
    assert len(answer.tool_calls) == 1
    assert answer.tool_calls[0].tool == "get_clients"
    assert any(c["id"] == client.id for c in answer.tool_calls[0].result["clients"])

    # second call to the provider must include the tool_result appended to messages
    assert len(provider.calls) == 2
    second_call_messages = provider.calls[1]["messages"]
    assert second_call_messages[-1]["role"] == "user"
    assert second_call_messages[-1]["content"][0]["type"] == "tool_result"
    assert second_call_messages[-1]["content"][0]["tool_use_id"] == "tu_1"


def test_loop_gives_up_after_max_iterations_without_crashing(db_session):
    _seed_one_client(db_session)
    # every call returns another tool_use -- the loop must bail out cleanly
    # rather than looping forever or raising.
    responses = [
        FakeResponse(stop_reason="tool_use", content=[FakeToolUseBlock(id=f"tu_{i}", name="get_clients", input={})])
        for i in range(10)
    ]
    provider = ScriptedProvider(responses)
    answer = answer_question(db_session, "Loop forever?", provider=provider)
    assert "unable to reach a final answer" in answer.text.lower()


def test_final_answer_is_scrubbed_even_if_the_model_ignored_the_system_prompt(db_session):
    """The system prompt tells the model never to surface an internal id, a
    filesystem path or a tool-call -- this proves that instruction is
    backstopped by app.agent.guard, not merely trusted: a model that leaks
    exactly that (as a real one occasionally will) still cannot make it out
    to the user, while the legitimate business content around it survives."""
    client = _seed_one_client(db_session)

    leaky_text = (
        f"{client.code} — Latest Reconciliation\n\n"
        "32 transactions processed, 100% associated with reconciliation groups.\n"
        "Evidence: get_batch_report(batch_id=145d4d3c-2a41-4e9a-9c11-8b1f9a7e2b0d) read from "
        r"C:\Users\ops\data\inbound\shyd\statement.csv."
        "\n1 open exception worth Rs 150.00 remains unexplained."
    )
    provider = ScriptedProvider([
        FakeResponse(stop_reason="end_turn", content=[FakeTextBlock(text=leaky_text)]),
    ])

    answer = answer_question(db_session, "Brief summary please.", provider=provider)

    assert "145d4d3c-2a41-4e9a-9c11-8b1f9a7e2b0d" not in answer.text
    assert "get_batch_report(" not in answer.text
    assert r"C:\Users" not in answer.text
    assert "statement.csv" not in answer.text
    # The actual financial content is untouched.
    assert "32 transactions processed" in answer.text
    assert "100% associated with reconciliation groups" in answer.text
    assert "Rs 150.00" in answer.text
