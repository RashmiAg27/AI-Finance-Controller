from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class Batch(Base):
    """A reconciliation run's unit of work: one client, one set of source files,
    one bound configuration version, one lifecycle.

    status/timestamps are the only mutable fields on this table (append-only
    tables record history elsewhere); every status change must go through
    app.domains.batches.state_machine.transition() so guard + audit_events stay
    centralized.
    """

    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    batch_code: Mapped[str] = mapped_column(String(128))
    config_version_id: Mapped[str] = mapped_column(ForeignKey("client_configurations.id"))
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)

    # Set when this run came from a configured BatchDefinition. Nullable
    # because an ad-hoc batch (uploaded files, a test fixture) is still a
    # legitimate batch with no standing instruction behind it.
    batch_definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("batch_definitions.id"), nullable=True, index=True
    )
    business_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    triggered_by_type: Mapped[str] = mapped_column(String(32), default="MANUAL")  # MANUAL | SCHEDULED | AGENT | ...
    triggered_by: Mapped[str] = mapped_column(String(128), default="system")

    # Live progress for the UI while the run executes in a worker thread.
    current_stage: Mapped[str | None] = mapped_column(String(48), nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    created_by: Mapped[str] = mapped_column(String(128), default="system")

    files_received_at: Mapped[datetime | None] = mapped_column(nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    normalized_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reconciliation_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reconciliation_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    exceptions_identified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    exceptions_resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    tax_processing_at: Mapped[datetime | None] = mapped_column(nullable=True)
    settlement_processing_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reporting_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    client: Mapped["Client"] = relationship()
    config_version: Mapped["ClientConfiguration"] = relationship()


class BatchFile(Base):
    """Join between a batch, the data source it fulfils, and the stored raw file."""

    __tablename__ = "batch_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"))
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
