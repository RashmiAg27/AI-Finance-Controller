from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base

INSTRUMENT_TYPES = (
    "NEFT", "RTGS", "IMPS", "UPI", "NACH", "CHEQUE",
    "BANK_CHARGES", "PAYMENT_GATEWAY_SETTLEMENT", "INTERNAL_TRANSFER", "OTHER",
)

# How the money actually moved. Distinct from instrument_type, which is the
# client's own classification vocabulary: payment_method is ours, and is what
# lets the engine reason about a UPI credit and a card settlement differently
# without knowing which client produced the row.
PAYMENT_METHODS = (
    "UPI", "NEFT", "RTGS", "IMPS", "NACH", "CHEQUE", "CASH", "NETBANKING",
    "DEBIT_CARD", "CREDIT_CARD", "POS", "WALLET", "PAYMENT_GATEWAY",
    "INTERNAL_TRANSFER", "TAX_PAYMENT", "EXCHANGE_SETTLEMENT", "OTHER",
)

# Who is on the other side. INTERNAL_ACCOUNT is the load-bearing one: a
# movement to another account the same client owns redistributes cash, it does
# not consume it, and the cash position must not treat it as an outflow.
COUNTERPARTY_TYPES = (
    "CUSTOMER", "VENDOR", "EMPLOYEE", "BANK", "TAX_AUTHORITY",
    "PAYMENT_AGGREGATOR", "CLEARING_HOUSE", "INTERNAL_ACCOUNT", "UNKNOWN",
)


class Transaction(Base):
    """The canonical financial transaction. Every heterogeneous source record
    is mapped into exactly one of these via a client's field_mappings — no
    downstream code branches on which source format produced it.

    Append-only: corrections happen via new batches, never by editing history.
    """

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    # The account this movement belongs to. Nullable because not every source
    # is account-bound (a payment-gateway transaction exists before it is
    # settled into any account), but bank-side rows always carry it.
    bank_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=True, index=True
    )
    source_id: Mapped[str] = mapped_column(String(64))  # data_sources.source_id (denormalized code)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"))

    canonical_reference: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)

    transaction_type: Mapped[str] = mapped_column(String(64))  # config-declared classification value
    instrument_type: Mapped[str] = mapped_column(String(32), default="OTHER", index=True)

    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    debit_credit: Mapped[str] = mapped_column(String(8))  # DEBIT | CREDIT

    # Gross/net decomposition carried on the row itself when the source states
    # it (a settlement report does; a bank statement does not). amount stays
    # the movement's own value -- these are what explain a gap to another side.
    fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    adjustment_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_type: Mapped[str] = mapped_column(String(24), default="UNKNOWN", index=True)
    counterparty_account: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="POSTED")
    source_system: Mapped[str] = mapped_column(String(64))

    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)


class TransactionIdentifier(Base):
    """One typed identifier extracted from a transaction's source row (e.g.
    UTR, TRADE_ID, PG_TXN_ID). identifier_type is whatever the client's config
    declares -- never a hardcoded interchangeable notion of "the" reference.

    linked_via_rule_id (nullable) records which identifier_linkage rule (if
    any) was resolved for this identifier at normalization time, so Pass 1/2
    matching can consult it directly instead of re-deriving linkage per
    comparison. NULL means this identifier has no configured linkage partner.
    """

    __tablename__ = "transaction_identifiers"
    __table_args__ = (UniqueConstraint("transaction_id", "identifier_type", name="uq_txn_identifier_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    client_id: Mapped[str] = mapped_column(String(36), index=True)  # denormalized for cross-client index safety

    identifier_type: Mapped[str] = mapped_column(String(64), index=True)
    value_raw: Mapped[str] = mapped_column(String(512))
    value_normalized: Mapped[str] = mapped_column(String(512), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    linked_via_rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
