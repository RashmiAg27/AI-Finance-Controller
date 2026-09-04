from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base

VERIFICATION_STATUSES = ("VERIFIED", "NOT_VERIFIED", "PROTOTYPE_ASSUMPTION")


class TaxRule(Base):
    """A versioned, sourced tax rule. Every rule must be traceable to an
    authoritative source and an effective period -- spec principle: never
    invent a rate, mark it NOT_VERIFIED instead of guessing (see
    docs/tax-rules.md for what was and wasn't confirmed against a primary
    source)."""

    __tablename__ = "tax_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    rule_version: Mapped[int] = mapped_column(default=1)

    client_scope: Mapped[str | None] = mapped_column(String(36), nullable=True)  # null = global/any client
    instrument_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # null = any instrument
    tax_type: Mapped[str] = mapped_column(String(16))  # GST | TDS | TCS | ...
    calculation_basis: Mapped[str] = mapped_column(String(64))  # e.g. "fee_amount"
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3))

    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    jurisdiction: Mapped[str] = mapped_column(String(32), default="IN")
    applicability: Mapped[str] = mapped_column(String(1024))  # scope + explicit exclusions, in plain language

    source_authority: Mapped[str] = mapped_column(String(128))
    source_reference: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    verification_status: Mapped[str] = mapped_column(String(24))
    verification_note: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)


class TaxCalculation(Base):
    """One applied calculation of a TaxRule against a specific match/pair of
    transactions -- the record that answers 'why was this tax amount
    calculated?' with the exact basis, rate, rule version, and source."""

    __tablename__ = "tax_calculations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tax_rule_id: Mapped[str] = mapped_column(ForeignKey("tax_rules.id"), index=True)
    reconciliation_match_id: Mapped[str | None] = mapped_column(
        ForeignKey("reconciliation_matches.id"), nullable=True, index=True
    )

    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))

    calculation_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
