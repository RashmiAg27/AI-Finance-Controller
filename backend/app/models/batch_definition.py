from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base

# What kind of reconciliation cycle this definition represents. Presentational
# + used by the agent to talk about batches the way an operations team does;
# the engine's behaviour is driven by source_ids and the client config, never
# by this value.
BATCH_TYPES = (
    "DAILY_STATEMENT", "SETTLEMENT_OBLIGATION", "POSITION_HOLDING",
    "COLLECTION_MANDATE", "FEE_INVOICE", "INTRADAY_SWEEP",
)
TRIGGER_TYPES = ("SCHEDULED", "FILE_ARRIVAL", "MANUAL", "UPSTREAM_EVENT")


class BatchDefinition(Base):
    """A *configured* batch: the standing instruction ("reconcile Meridian's
    bank statement against the ERP ledger every evening at 19:30, files arrive
    in this directory"). Each execution of it creates a Batch row -- the
    definition is the template, the Batch is the run.

    Everything here is operator-editable from the Reconciliation window; edits
    take effect on the next run, never retroactively on a run in flight (a
    Batch binds its config_version_id at creation).
    """

    __tablename__ = "batch_definitions"
    __table_args__ = (UniqueConstraint("client_id", "code", name="uq_batch_definition_per_client"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    batch_type: Mapped[str] = mapped_column(String(32), default="DAILY_STATEMENT")

    # WHAT proof this cycle produces -- see domains.reconciliation.types. The
    # engine's passes are the same; what differs is which sides are compared,
    # what the natural key is, and which differences are legitimate.
    reconciliation_type: Mapped[str] = mapped_column(String(32), default="BANK_GL", index=True)

    # WHICH account this cycle reconciles. Null only for the reconciliation
    # types that genuinely are not account-scoped (payments to a settlement
    # batch, a transfer spanning two accounts, a TDS deduction chain).
    bank_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=True, index=True
    )

    trigger_type: Mapped[str] = mapped_column(String(32), default="MANUAL")
    trigger_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)  # cron text, event name, ...

    import_source_id: Mapped[str | None] = mapped_column(ForeignKey("import_sources.id"), nullable=True)

    # Which of the client's configured data_sources this batch expects. This --
    # not DataSource.is_required -- is what completeness is checked against,
    # because one client's sources serve several different batch cycles.
    source_ids: Mapped[list] = mapped_column(JSON, default=list)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cutoff_time: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "19:30 IST"
    sla_minutes: Mapped[int] = mapped_column(Integer, default=60)
    owner_team: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    updated_at: Mapped[datetime] = mapped_column(default=default_clock.now, onupdate=default_clock.now)
    updated_by: Mapped[str] = mapped_column(String(128), default="system")

    client: Mapped["Client"] = relationship()
    import_source: Mapped["ImportSource | None"] = relationship()
    bank_account: Mapped["BankAccount | None"] = relationship()
