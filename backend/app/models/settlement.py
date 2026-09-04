from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class Settlement(Base):
    """Formal gross -> deductions -> net decomposition for one reconciled
    group of transactions (an AGGREGATED or EXPLAINED_BY_FEE_TAX match).
    Reuses M4's grouping and M3's tax calculation rather than recomputing
    either -- this table is the place that answers 'why is the bank credit
    lower than the gross amount?' with a full, itemized breakdown."""

    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    reconciliation_match_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_matches.id"), unique=True)

    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    net_amount_expected: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    net_amount_observed: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    is_fully_explained: Mapped[bool] = mapped_column(Boolean)

    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)


class SettlementComponent(Base):
    """One itemized deduction line (fee, tax-on-fee, other) within a
    settlement's decomposition."""

    __tablename__ = "settlement_components"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    settlement_id: Mapped[str] = mapped_column(ForeignKey("settlements.id"), index=True)
    component_type: Mapped[str] = mapped_column(String(32))  # FEE | TAX_ON_FEE | OTHER_DEDUCTION
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    description: Mapped[str] = mapped_column(String(512))
    tax_rule_id: Mapped[str | None] = mapped_column(ForeignKey("tax_rules.id"), nullable=True)
