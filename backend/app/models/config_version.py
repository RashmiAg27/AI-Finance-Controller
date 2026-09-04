from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class ClientConfiguration(Base):
    """A versioned, immutable snapshot of one client's full configuration.

    Append-only: 'editing' a config means creating a new version row, never
    mutating raw_yaml/parsed_json of an existing one. A batch binds to whichever
    version is ACTIVE at batch-creation time (see Batch.config_version_id),
    which is what makes a reconciliation run reproducible after the fact.
    """

    __tablename__ = "client_configurations"
    __table_args__ = (UniqueConstraint("client_id", "version", name="uq_client_config_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64))
    raw_yaml: Mapped[str] = mapped_column(Text)
    parsed_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # DRAFT | ACTIVE | ARCHIVED
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    created_by: Mapped[str] = mapped_column(String(128), default="system")
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    client: Mapped["Client"] = relationship(back_populates="configurations")
