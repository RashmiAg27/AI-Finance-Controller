from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class Client(Base):
    """First-class tenant. No client-specific behaviour ever lives in Python —
    only in the versioned ClientConfiguration this client owns."""

    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")  # ACTIVE | SUSPENDED
    # Display-only preference, not a processing rule -- unlike everything in
    # ClientConfiguration, changing it can never alter a reconciliation
    # outcome. It controls only how already-UTC timestamps are rendered for
    # this client (see app.core.timezone), an IANA zone name like
    # "Asia/Kolkata". Every stored timestamp remains UTC regardless.
    display_timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)

    configurations: Mapped[list["ClientConfiguration"]] = relationship(back_populates="client")
    data_sources: Mapped[list["DataSource"]] = relationship(back_populates="client")
