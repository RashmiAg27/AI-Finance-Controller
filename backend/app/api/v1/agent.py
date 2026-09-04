from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.controller import answer_question, converse
from app.agent.tools import TOOL_REGISTRY
from app.api.deps import get_db
from app.schemas.agent import AgentChatRequest, AgentQueryRequest, AgentQueryResponse, ToolCallResponse

router = APIRouter(prefix="/agent", tags=["agent"])


def _to_response(answer) -> AgentQueryResponse:
    return AgentQueryResponse(
        text=answer.text,
        tool_calls=[ToolCallResponse(tool=t.tool, input=t.input, result=t.result) for t in answer.tool_calls],
        configured=answer.configured,
        ui_hint=answer.ui_hint,
        awaiting_confirmation=answer.awaiting_confirmation,
        tools_available=sorted(TOOL_REGISTRY),
    )


@router.post("/query", response_model=AgentQueryResponse)
def query_agent(payload: AgentQueryRequest, db: Session = Depends(get_db)):
    return _to_response(answer_question(db, payload.question, scope_client_id=payload.client_id))


@router.post("/chat", response_model=AgentQueryResponse)
def chat_agent(payload: AgentChatRequest, db: Session = Depends(get_db)):
    """Multi-turn conversation. The confirmation protocol needs the previous
    turn's proposal and the user's answer to it in the same request, so the
    panel resends the whole transcript rather than relying on server session
    state."""
    history = [{"role": m.role, "content": m.content} for m in payload.messages]
    return _to_response(converse(db, history, scope_client_id=payload.client_id, actor="operator-via-agent"))
