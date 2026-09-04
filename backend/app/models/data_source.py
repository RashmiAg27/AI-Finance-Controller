from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class DataSource(Base):
    """Declares one of a client's input feeds (e.g. 'bank_statement', 'internal_ledger').

    Synced from the ACTIVE ClientConfiguration on activation; mutable because it
    mirrors current config rather than being an audit record itself (the config
    version row is the audit record).
    """

    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("client_id", "source_id", name="uq_data_source_per_client"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(64))  # config-declared code, e.g. "bank_statement"
    name: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(16))  # CSV | XLSX | JSON | PDF
    role: Mapped[str] = mapped_column(String(16))  # INTERNAL | EXTERNAL
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)

    client: Mapped["Client"] = relationship(back_populates="data_sources")
