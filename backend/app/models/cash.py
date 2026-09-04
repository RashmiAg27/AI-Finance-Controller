from datetime import date as date_, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class CashPosition(Base):
    """A point-in-time snapshot of a client's cash state, computed from
    confirmed matches, settlements, and open exceptions -- never a forecast
    presented as fact. Recomputed (new row) whenever a batch closes rather
    than mutated in place, so historical positions stay auditable."""

    __tablename__ = "cash_positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"))
    as_of: Mapped[date_] = mapped_column(Date)

    confirmed_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    pending_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expected_inflows: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expected_outflows: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    unreconciled_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))

    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)


class CashForecast(Base):
    """A short-term, explicitly-labeled-as-a-prototype-assumption forecast.
    Never confused with CashPosition -- this table is uncertain by
    construction and always carries the drivers behind its number."""

    __tablename__ = "cash_forecasts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    cash_position_id: Mapped[str] = mapped_column(ForeignKey("cash_positions.id"))

    horizon_days: Mapped[int] = mapped_column()
    as_of: Mapped[date_] = mapped_column(Date)
    expected_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    low_estimate: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    high_estimate: Mapped[Decimal] = mapped_column(Numeric(18, 2))

    drivers: Mapped[dict] = mapped_column(JSON, default=dict)
    assumptions_note: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
