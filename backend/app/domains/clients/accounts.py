"""A client's bank accounts -- the reconciliation units.

Deliberately thin: an account is reference data that batches and transactions
point at. What it earns us is the ability to say "this break is in HDFC
operating, not in ICICI collections", which is the difference between a
reconciliation an operator can act on and a pile of unexplained netting.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_event
from app.core.errors import DomainError, NotFoundError
from app.models.bank_account import ACCOUNT_PURPOSES, ACCOUNT_TYPES, BankAccount

_EDITABLE = {
    "display_name", "bank_name", "account_number_masked", "ifsc", "branch",
    "account_type", "purpose", "currency", "gl_code", "is_active",
}


def list_accounts(db: Session, client_id: str, *, active_only: bool = False) -> list[BankAccount]:
    stmt = select(BankAccount).where(BankAccount.client_id == client_id)
    if active_only:
        stmt = stmt.where(BankAccount.is_active.is_(True))
    return list(db.execute(stmt.order_by(BankAccount.bank_name, BankAccount.account_code)).scalars())


def get_account(db: Session, account_id: str) -> BankAccount:
    row = db.get(BankAccount, account_id)
    if row is None:
        raise NotFoundError("BankAccount", account_id)
    return row


def create_account(db: Session, *, client_id: str, account_code: str, display_name: str,
                   bank_name: str, account_number_masked: str, ifsc: str | None = None,
                   branch: str | None = None, account_type: str = "CURRENT",
                   purpose: str = "OPERATING", currency: str = "INR",
                   gl_code: str | None = None, actor: str = "system") -> BankAccount:
    _validate(account_type=account_type, purpose=purpose)
    row = BankAccount(
        client_id=client_id, account_code=account_code, display_name=display_name,
        bank_name=bank_name, account_number_masked=account_number_masked, ifsc=ifsc, branch=branch,
        account_type=account_type, purpose=purpose, currency=currency, gl_code=gl_code,
    )
    db.add(row)
    db.flush()
    record_event(db, entity_type="BANK_ACCOUNT", entity_id=row.id, event_type="BANK_ACCOUNT_CREATED",
                 payload={"client_id": client_id, "account_code": account_code, "bank": bank_name},
                 actor=actor)
    return row


def update_account(db: Session, account_id: str, patch: dict[str, Any], *, actor: str = "system") -> BankAccount:
    row = get_account(db, account_id)
    unknown = sorted(set(patch) - _EDITABLE)
    if unknown:
        raise DomainError(f"cannot edit field(s) {unknown} on a bank account; editable: {sorted(_EDITABLE)}")
    _validate(
        account_type=patch.get("account_type", row.account_type),
        purpose=patch.get("purpose", row.purpose),
    )
    before = {f: getattr(row, f) for f in patch}
    for field, value in patch.items():
        setattr(row, field, value)
    db.flush()
    record_event(db, entity_type="BANK_ACCOUNT", entity_id=row.id, event_type="BANK_ACCOUNT_UPDATED",
                 payload={"before": before, "after": {f: getattr(row, f) for f in patch}}, actor=actor)
    return row


def _validate(*, account_type: str, purpose: str) -> None:
    if account_type not in ACCOUNT_TYPES:
        raise DomainError(f"unknown account_type {account_type!r}; expected one of {list(ACCOUNT_TYPES)}")
    if purpose not in ACCOUNT_PURPOSES:
        raise DomainError(f"unknown purpose {purpose!r}; expected one of {list(ACCOUNT_PURPOSES)}")
