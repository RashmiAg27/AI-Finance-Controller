from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base

# Reserved values beyond what the MVP's deterministic passes produce (COMPOSITE_SCORED,
# ML_ASSISTED, MANUAL) are declared here even before their pass exists, so no migration
# is needed when M5b (ML) lands.
MATCH_TYPES = (
    "EXACT_REFERENCE", "NORMALIZED_REFERENCE", "AMOUNT_DATE",
    "AMOUNT_COUNTERPARTY_DATE_INSTRUMENT", "EXPLAINED_BY_FEE_TAX", "AGGREGATED",
    "COMPOSITE_SCORED", "ML_ASSISTED", "MANUAL",
)
CARDINALITIES = ("ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "MANY_TO_MANY")


class ReconciliationRun(Base):
    """One execution of the matching engine over a batch. Re-running creates a
    new row (append-only) rather than overwriting -- reproducibility requires
    being able to compare runs, not just see the latest."""

    __tablename__ = "reconciliation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    run_number: Mapped[int] = mapped_column(Integer)
    config_version_id: Mapped[str] = mapped_column(ForeignKey("client_configurations.id"))
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")  # RUNNING | COMPLETED | FAILED
    started_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stats_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ReconciliationMatch(Base):
    """One matching decision made by the engine. Never a bare boolean -- always
    accompanied by MatchEvidence rows explaining *why*.

    Cardinality is not two FK columns -- it's derived from how many rows point
    at this match on each `side` of ReconciliationMatchTransaction, which is
    what lets 1:N/N:1 aggregation (M4) plug in without a schema change.
    """

    __tablename__ = "reconciliation_matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reconciliation_run_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    match_type: Mapped[str] = mapped_column(String(32))
    cardinality: Mapped[str] = mapped_column(String(16), default="ONE_TO_ONE")
    rule_id: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="CONFIRMED")  # PROPOSED|CONFIRMED|REJECTED|SUPERSEDED
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)


class ReconciliationMatchTransaction(Base):
    __tablename__ = "reconciliation_match_transactions"
    __table_args__ = (UniqueConstraint("match_id", "transaction_id", name="uq_match_transaction"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_matches.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    side: Mapped[str] = mapped_column(String(8))  # SOURCE | TARGET
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)


class MatchEvidence(Base):
    __tablename__ = "match_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_matches.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64))
    field_name: Mapped[str] = mapped_column(String(64))
    source_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    comparator: Mapped[str] = mapped_column(String(64))
    passed: Mapped[bool] = mapped_column(Boolean)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
