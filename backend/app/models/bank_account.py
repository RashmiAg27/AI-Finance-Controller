from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base

# What the account is used for. This is not decoration: an account's purpose
# is what makes a movement between two of the client's own accounts a
# redistribution rather than a cash outflow.
ACCOUNT_PURPOSES = (
    "OPERATING", "COLLECTIONS", "DISBURSAL", "SETTLEMENT",
    "CLIENT_FUNDS", "PAYROLL", "TAX", "ESCROW",
)
ACCOUNT_TYPES = ("CURRENT", "SAVINGS", "CASH_CREDIT", "OVERDRAFT", "NOSTRO")


class BankAccount(Base):
    """A client's bank account -- and the actual unit of reconciliation.

    This is the correction that matters most in the model: a client is the
    parent entity, but you never reconcile "a client" against "a bank
    statement". Meridian holds accounts at HDFC, ICICI and Axis; each has its
    own statement, its own ledger entries, and its own reconciliation cycle.
    Pooling them would net unrelated movements against each other and make
    every break unexplainable.

    A batch that reconciles a bank feed is therefore scoped to exactly one
    account, and every transaction it produces carries that account's id.
    """

    __tablename__ = "bank_accounts"
    __table_args__ = (UniqueConstraint("client_id", "account_code", name="uq_bank_account_per_client"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)

    account_code: Mapped[str] = mapped_column(String(64))  # internal handle, e.g. "HDFC_OPERATING"
    display_name: Mapped[str] = mapped_column(String(255))
    bank_name: Mapped[str] = mapped_column(String(128))
    account_number_masked: Mapped[str] = mapped_column(String(64))
    ifsc: Mapped[str | None] = mapped_column(String(16), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

    account_type: Mapped[str] = mapped_column(String(24), default="CURRENT")
    purpose: Mapped[str] = mapped_column(String(24), default="OPERATING")
    currency: Mapped[str] = mapped_column(String(3), default="INR")

    # A ledger code lets the GL side of a Bank<->GL reconciliation say which
    # account a journal line belongs to without repeating the account number.
    gl_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    updated_at: Mapped[datetime] = mapped_column(default=default_clock.now, onupdate=default_clock.now)

    client: Mapped["Client"] = relationship()

    @property
    def label(self) -> str:
        return f"{self.bank_name} {self.account_number_masked}"
