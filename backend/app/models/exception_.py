from datetime import datetime

from sqlalchemy import Float, ForeignKey, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base

EXCEPTION_TYPES = (
    "AMOUNT_MISMATCH", "REFERENCE_MISMATCH", "COUNTERPARTY_MISMATCH",
    "MISSING_INTERNAL_RECORD", "MISSING_EXTERNAL_RECORD", "DUPLICATE",
    "TIMING_DIFFERENCE", "OUTSTANDING_PAYMENT", "OUTSTANDING_RECEIPT",
    "FEE_VARIANCE", "TAX_VARIANCE", "UNEXPLAINED",
)
EXCEPTION_STATUSES = (
    "OPEN", "UNDER_REVIEW", "RESOLVED", "RESOLVED_VIA_TAX",
    "RESOLVED_VIA_SETTLEMENT", "WRITE_OFF", "FALSE_POSITIVE",
)


class Exception_(Base):
    """One unresolved/ambiguous item. Mutable in place (status/last_seen_at) --
    every mutation should emit an AuditEvent."""

    __tablename__ = "exceptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    reconciliation_run_id: Mapped[str | None] = mapped_column(ForeignKey("reconciliation_runs.id"), nullable=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)

    exception_type: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")  # LOW|MEDIUM|HIGH|CRITICAL
    status: Mapped[str] = mapped_column(String(24), default="OPEN", index=True)

    amount_impact: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    likely_cause: Mapped[str | None] = mapped_column(String(512), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(512), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    last_seen_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    updated_at: Mapped[datetime] = mapped_column(default=default_clock.now)

    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(512), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ExceptionEvidence(Base):
    __tablename__ = "exception_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exception_id: Mapped[str] = mapped_column(ForeignKey("exceptions.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64))
    field_name: Mapped[str] = mapped_column(String(64))
    value_observed: Mapped[str | None] = mapped_column(String(512), nullable=True)
    comparator: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)


class ExceptionTransaction(Base):
    """Links an exception to more than one transaction (e.g. DUPLICATE)."""

    __tablename__ = "exception_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exception_id: Mapped[str] = mapped_column(ForeignKey("exceptions.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="RELATED")  # PRIMARY | RELATED
