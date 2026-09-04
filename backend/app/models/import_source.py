from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base

# How a batch's files physically arrive. LOCAL_DIRECTORY is genuinely read off
# this machine's filesystem; the remaining three are simulated against a
# per-connection landing area under data/simulated/ so the operator-facing
# behaviour (poll, discover, fetch, log) is identical without needing a live
# mail server, SFTP host, or vendor API in a prototype.
IMPORT_SOURCE_KINDS = ("LOCAL_DIRECTORY", "EMAIL_INBOX", "SFTP_CONNECTION", "API_CONNECTION")


class ImportSource(Base):
    """A client's configured way of receiving files for one or more batches.

    connection_json is deliberately schemaless at the ORM layer -- its shape
    depends on `kind` and is validated by
    app.schemas.import_source.validate_connection() so a new kind can be added
    without a migration.
    """

    __tablename__ = "import_sources"
    __table_args__ = (UniqueConstraint("client_id", "code", name="uq_import_source_per_client"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))
    connection_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Result of the most recent discovery attempt -- what the operator sees in
    # the "Last poll" column without having to open a batch log.
    last_polled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # OK | EMPTY | ERROR
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    updated_at: Mapped[datetime] = mapped_column(default=default_clock.now, onupdate=default_clock.now)
    updated_by: Mapped[str] = mapped_column(String(128), default="system")

    client: Mapped["Client"] = relationship()
