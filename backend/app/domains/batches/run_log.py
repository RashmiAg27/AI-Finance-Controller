"""Writes the operator-facing batch log.

Kept separate from app.core.audit deliberately: the audit trail answers "what
did the system do to this record, and who authorised it"; this answers "what
would I have seen on screen while the run was executing". Exceptions are
written here too, in full, so the batch log is the single place an operator
(or the agent, reading it back) can explain a run without cross-referencing
four tables.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch_log import BatchLogEntry


def _next_seq(db: Session, batch_id: str) -> int:
    current = db.execute(
        select(func.max(BatchLogEntry.seq)).where(BatchLogEntry.batch_id == batch_id)
    ).scalar_one_or_none()
    return (current or 0) + 1


def log(db: Session, batch_id: str, stage: str, message: str, *,
        level: str = "INFO", detail: dict | None = None) -> BatchLogEntry:
    entry = BatchLogEntry(
        batch_id=batch_id, seq=_next_seq(db, batch_id), level=level,
        stage=stage, message=message, detail_json=detail or {},
    )
    db.add(entry)
    db.flush()
    return entry


def log_many(db: Session, batch_id: str, stage: str, messages: list[str], *, level: str = "INFO") -> None:
    seq = _next_seq(db, batch_id)
    for offset, message in enumerate(messages):
        db.add(BatchLogEntry(batch_id=batch_id, seq=seq + offset, level=level, stage=stage,
                             message=message, detail_json={}))
    db.flush()


def entries(db: Session, batch_id: str, *, since_seq: int = 0) -> list[BatchLogEntry]:
    return list(db.execute(
        select(BatchLogEntry)
        .where(BatchLogEntry.batch_id == batch_id, BatchLogEntry.seq > since_seq)
        .order_by(BatchLogEntry.seq)
    ).scalars())
