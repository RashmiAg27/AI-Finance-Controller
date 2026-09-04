"""Tools that let the agent answer the harder half of the questions.

Everything here is read-only and returns *arithmetic the operator can check*,
not a narrative. When the agent says a gap is explained, it must be able to
show the line-by-line sum that explains it -- which is why
explain_amount_difference returns the workings rather than a verdict.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.serialize import to_jsonable
from app.domains.clients import config_editor
from app.domains.reconciliation import types as recon_types
from app.domains.tax.service import calculate_fee_and_tax
from app.models.bank_account import BankAccount
from app.models.batch import Batch
from app.models.batch_definition import BatchDefinition
from app.models.cash import CashPosition
from app.models.exception_ import Exception_
from app.models.transaction import Transaction


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f"{value!r} is not a number")


def list_reconciliation_types(_ctx) -> dict:
    """The catalogue of proofs the platform performs, with the sides each one
    compares and which differences are legitimate for it. Use this before
    calling a gap a break: a ₹10,000 sale against a ₹9,764 settlement is
    expected under PAYMENT_SETTLEMENT and alarming under BANK_GL."""
    return {"reconciliation_types": recon_types.catalogue()}


def get_bank_accounts(ctx, client_id: str) -> dict:
    """A client's bank accounts -- the units reconciliation actually happens
    against. A client is never reconciled as a whole."""
    ctx.check_client(client_id)
    rows = list(ctx.db.execute(
        select(BankAccount).where(BankAccount.client_id == client_id).order_by(BankAccount.account_code)
    ).scalars())
    return to_jsonable({"client_id": client_id, "bank_accounts": [
        {"bank_account_id": a.id, "account_code": a.account_code, "display_name": a.display_name,
         "bank": a.bank_name, "account_number": a.account_number_masked, "ifsc": a.ifsc,
         "purpose": a.purpose, "account_type": a.account_type, "gl_code": a.gl_code,
         "currency": a.currency, "is_active": a.is_active}
        for a in rows
    ]})


def get_account_position(ctx, client_id: str) -> dict:
    """Cash broken down by account, plus the internal-transfer volume that was
    deliberately excluded from the total. Answers 'where is the money', which
    a single client-level figure cannot."""
    ctx.check_client(client_id)
    position = ctx.db.execute(
        select(CashPosition).where(CashPosition.client_id == client_id)
        .order_by(CashPosition.created_at.desc())
    ).scalars().first()
    if position is None:
        return {"error": f"No cash position has been computed yet for client_id={client_id!r}."}

    detail = position.detail or {}
    by_account = detail.get("by_bank_account", {})
    labelled = []
    for account_id, amount in by_account.items():
        account = ctx.db.get(BankAccount, account_id)
        labelled.append({
            "bank_account_id": account_id,
            "account": f"{account.bank_name} {account.account_number_masked}" if account else account_id,
            "purpose": account.purpose if account else None,
            "reconciled_net_movement": amount,
        })

    return to_jsonable({
        "client_id": client_id,
        "as_of": position.as_of,
        "confirmed_cash": position.confirmed_cash,
        "unreconciled_amount": position.unreconciled_amount,
        "by_account": labelled,
        "internal_transfer_volume": detail.get("internal_transfer_volume"),
        "internal_transfer_note": detail.get("internal_transfer_note"),
    })


def explain_amount_difference(ctx, client_id: str, gross_amount: str, observed_amount: str,
                              instrument_type: str | None = None) -> dict:
    """Given a gross figure and what actually arrived, work out whether the
    client's configured fee, tax, commission and statutory charges account for
    the gap -- and return the arithmetic line by line.

    This is the tool for "why is the bank credit smaller than the invoice?".
    It never asserts a conclusion the numbers do not support: if the residual
    is non-zero it says so and reports the residual.
    """
    ctx.check_client(client_id)
    try:
        gross = _decimal(gross_amount)
        observed = _decimal(observed_amount)
    except ValueError as exc:
        return {"error": str(exc)}

    config = config_editor.active_config(ctx.db, client_id)
    if config.tax_fee_rules is None:
        return {"error": "This client has no fee/tax treatment configured, so no configured rule "
                          "can explain a difference. The gap must be investigated as an exception."}

    calc = calculate_fee_and_tax(ctx.db, gross, config.tax_fee_rules, instrument_type=instrument_type)
    residual = observed - calc.net_amount
    tolerance = Decimal(str(config.tax_fee_rules.rounding_tolerance))

    workings = [
        {"label": "Gross amount", "amount": str(gross), "sign": "+"},
        {"label": f"Processing fee at {calc.fee_rate_percent}%", "amount": str(calc.fee_amount),
         "sign": "-", "verification_status": config.tax_fee_rules.fee.verification_status},
        {"label": f"{calc.tax_rule.tax_type} on fee at {calc.tax_rate_percent}%",
         "amount": str(calc.tax_amount), "sign": "-",
         "verification_status": calc.tax_rule.verification_status,
         "source_reference": calc.tax_rule.source_reference},
    ]
    for line in calc.charge_lines:
        workings.append({
            "label": f"{line.label} at {line.rate_percent}% on {line.basis.lower()}",
            "amount": str(line.amount), "sign": "-",
            "verification_status": line.verification_status,
            "source_reference": line.source_reference,
        })

    return to_jsonable({
        "client_id": client_id,
        "instrument_type": instrument_type,
        "workings": workings,
        "expected_net": str(calc.net_amount),
        "observed_net": str(observed),
        "total_deductions": str(calc.total_deductions),
        "residual": str(residual),
        "rounding_tolerance": str(tolerance),
        "fully_explained": abs(residual) <= tolerance,
        "verdict": (
            "The configured fee, tax and charges fully account for the difference."
            if abs(residual) <= tolerance else
            f"The configured rules explain {calc.total_deductions} of the gap; {abs(residual)} remains "
            "unexplained and must be investigated rather than absorbed."
        ),
    })


def search_transactions(ctx, client_id: str, min_amount: str | None = None,
                        max_amount: str | None = None, counterparty: str | None = None,
                        payment_method: str | None = None, source_id: str | None = None,
                        bank_account_id: str | None = None, limit: int = 25) -> dict:
    """Find transactions by the attributes an operator actually asks about --
    amount range, counterparty, how the money moved, which feed it came from,
    which account it belongs to."""
    ctx.check_client(client_id)
    stmt = select(Transaction).where(Transaction.client_id == client_id)

    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= _decimal(min_amount))
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= _decimal(max_amount))
    if counterparty:
        stmt = stmt.where(Transaction.counterparty.ilike(f"%{counterparty}%"))
    if payment_method:
        stmt = stmt.where(Transaction.payment_method == payment_method.upper())
    if source_id:
        stmt = stmt.where(Transaction.source_id == source_id)
    if bank_account_id:
        stmt = stmt.where(Transaction.bank_account_id == bank_account_id)

    limit = max(1, min(limit, 100))
    total = ctx.db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()
    rows = list(ctx.db.execute(stmt.order_by(Transaction.amount.desc()).limit(limit)).scalars())

    return to_jsonable({
        "client_id": client_id, "matched_count": total, "returned": len(rows),
        "truncated": total > len(rows),
        "transactions": [
            {"transaction_id": t.id, "source_id": t.source_id, "reference": t.canonical_reference,
             "amount": t.amount, "debit_credit": t.debit_credit, "currency": t.currency,
             "transaction_date": t.transaction_date, "counterparty": t.counterparty,
             "counterparty_type": t.counterparty_type, "payment_method": t.payment_method,
             "instrument_type": t.instrument_type, "description": t.description,
             "bank_account_id": t.bank_account_id}
            for t in rows
        ],
    })


def aggregate_exceptions(ctx, client_id: str, group_by: str = "exception_type") -> dict:
    """Totals and money-at-risk for a client's open exceptions, grouped the way
    the question was asked: by type, severity, batch, or reconciliation type."""
    ctx.check_client(client_id)
    allowed = {"exception_type", "severity", "batch", "reconciliation_type"}
    if group_by not in allowed:
        return {"error": f"group_by must be one of {sorted(allowed)}"}

    batch_ids = list(ctx.db.execute(select(Batch.id).where(Batch.client_id == client_id)).scalars())
    if not batch_ids:
        return {"client_id": client_id, "groups": [], "note": "no batches have been run for this client"}

    exceptions = list(ctx.db.execute(
        select(Exception_).where(Exception_.batch_id.in_(batch_ids), Exception_.status == "OPEN")
    ).scalars())

    def key_for(exc: Exception_) -> str:
        if group_by == "exception_type":
            return exc.exception_type
        if group_by == "severity":
            return exc.severity
        batch = ctx.db.get(Batch, exc.batch_id)
        if group_by == "batch":
            return batch.batch_code if batch else exc.batch_id
        definition = ctx.db.get(BatchDefinition, batch.batch_definition_id) if batch and batch.batch_definition_id else None
        return definition.reconciliation_type if definition else "UNKNOWN"

    groups: dict[str, dict] = {}
    for exc in exceptions:
        key = key_for(exc)
        entry = groups.setdefault(key, {"key": key, "count": 0, "amount_at_risk": Decimal(0)})
        entry["count"] += 1
        entry["amount_at_risk"] += exc.amount_impact or Decimal(0)

    ordered = sorted(groups.values(), key=lambda g: g["amount_at_risk"], reverse=True)
    return to_jsonable({
        "client_id": client_id, "group_by": group_by,
        "open_exception_count": len(exceptions),
        "total_amount_at_risk": sum((g["amount_at_risk"] for g in ordered), Decimal(0)),
        "groups": ordered,
    })
