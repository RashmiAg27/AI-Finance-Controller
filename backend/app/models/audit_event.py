from datetime import datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class AuditEvent(Base):
    """Append-only record of lifecycle/state/config/admin-level events (batch
    transitions, config activation, exception status changes). Granular
    per-transaction reasoning lives in match_evidence/exception_evidence
    instead, so this table doesn't get one row per transaction."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)  # BATCH | CONFIG | EXCEPTION | ...
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
