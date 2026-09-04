from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base

LEVELS = ("INFO", "WARN", "ERROR", "EXCEPTION")


class BatchLogEntry(Base):
    """Append-only operator-facing run log for one batch execution.

    Distinct from AuditEvent on purpose: AuditEvent records *what the system
    did to a record* for compliance, this records *what an operator watching
    the run would see* -- import discovery, per-stage progress, per-exception
    detail, and the failure that stopped it. Both are written; neither
    replaces the other.
    """

    __tablename__ = "batch_log_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    stage: Mapped[str] = mapped_column(String(48))  # IMPORT | VALIDATE | NORMALIZE | MATCH | EXCEPTIONS | TAX | ...
    message: Mapped[str] = mapped_column(Text)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
