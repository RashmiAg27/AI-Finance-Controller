from typing import Literal

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    question: str
    client_id: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentChatRequest(BaseModel):
    """The full visible transcript, resent each turn. The server holds no
    session state, which is what lets the confirmation protocol work: the
    agent proposes a run on one turn and executes it on the next only because
    the user's agreement is right there in the history it is given."""

    messages: list[ChatMessage]
    client_id: str | None = None


class ToolCallResponse(BaseModel):
    tool: str
    input: dict
    result: dict


class AgentQueryResponse(BaseModel):
    text: str
    tool_calls: list[ToolCallResponse]
    configured: bool
    # Set when the turn produced something the UI should show: the batch the
    # agent just started, the window it acted on.
    ui_hint: dict | None = None
    # Set when a state-changing tool refused to act and is waiting for the
    # user to agree -- the panel renders the plan with Yes/No buttons.
    awaiting_confirmation: dict | None = None
    tools_available: list[str] = Field(default_factory=list)
