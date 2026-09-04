"""Cash position: separates actual/confirmed cash (from matched external
transactions -- the bank/gateway's own record of money movement) from
pending (settlements whose net value is still disputed) and expected
(internal transactions awaiting external confirmation, i.e. still open as
MISSING_EXTERNAL_RECORD exceptions). unreconciled_amount is the honest
"amount at risk" figure the spec repeatedly asks for -- the sum of every
still-open exception's amount_impact, never hidden or netted away.

Never presents a forecast as an actual balance -- that distinction is the
whole reason CashForecast is a separate table (see app.domains.forecasting).
"""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.batch import Batch
from app.models.cash import CashPosition
from app.models.client import Client
from app.models.config_version import ClientConfiguration
from app.models.exception_ import Exception_
from app.models.reconciliation import ReconciliationMatch, ReconciliationMatchTransaction
from app.models.settlement import Settlement
from app.models.transaction import Transaction
from app.schemas.config import ClientConfigSchema


def _client_data_source_roles(db: Session, batch: Batch) -> dict[str, str]:
    config_row = db.get(ClientConfiguration, batch.config_version_id)
    config = ClientConfigSchema.model_validate(config_row.parsed_json)
    return {ds.source_id: ds.role for ds in config.data_sources}


def compute_cash_position(db: Session, client_id: str, as_of_batch: Batch) -> CashPosition:
    client = db.get(Client, client_id)
    if client is None:
        raise NotFoundError("Client", client_id)

    client_batches = list(db.execute(select(Batch.id).where(Batch.client_id == client_id)).scalars())
    role_by_source: dict[str, str] = {}
    for batch_id in client_batches:
        batch = db.get(Batch, batch_id)
        role_by_source.update(_client_data_source_roles(db, batch))

    confirmed_matched_txn_ids = set(
        db.execute(
            select(ReconciliationMatchTransaction.transaction_id)
            .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchTransaction.match_id)
            .where(ReconciliationMatch.status == "CONFIRMED")
        ).scalars()
    )

    confirmed_cash = Decimal(0)
    internal_transfer_volume = Decimal(0)
    by_account: dict[str, Decimal] = {}
    if confirmed_matched_txn_ids and client_batches:
        external_matched = list(
            db.execute(
                select(Transaction).where(
                    Transaction.id.in_(confirmed_matched_txn_ids),
                    Transaction.batch_id.in_(client_batches),
                )
            ).scalars()
        )
        for txn in external_matched:
            if role_by_source.get(txn.source_id) != "EXTERNAL":
                continue
            signed = txn.amount if txn.debit_credit == "CREDIT" else -txn.amount

            # A sweep between two accounts the client owns changes WHERE the
            # money sits, not HOW MUCH there is. Both legs are real bank
            # movements and both are reconciled, but summing them into the
            # cash position would double-count the transfer -- once as an
            # outflow from the source account and once as an inflow to the
            # destination. Track it per account instead, and leave the total
            # alone.
            if txn.counterparty_type == "INTERNAL_ACCOUNT":
                internal_transfer_volume += txn.amount
                if txn.bank_account_id:
                    by_account[txn.bank_account_id] = by_account.get(txn.bank_account_id, Decimal(0)) + signed
                continue

            confirmed_cash += signed
            if txn.bank_account_id:
                by_account[txn.bank_account_id] = by_account.get(txn.bank_account_id, Decimal(0)) + signed

    pending_cash = Decimal(0)
    unexplained_settlements = list(
        db.execute(
            select(Settlement).where(Settlement.batch_id.in_(client_batches), Settlement.is_fully_explained.is_(False))
        ).scalars()
    ) if client_batches else []
    for s in unexplained_settlements:
        pending_cash += s.net_amount_observed

    open_exceptions = list(
        db.execute(
            select(Exception_).where(Exception_.batch_id.in_(client_batches), Exception_.status == "OPEN")
        ).scalars()
    ) if client_batches else []

    expected_inflows = Decimal(0)
    expected_outflows = Decimal(0)
    unreconciled_amount = Decimal(0)
    for exc in open_exceptions:
        amount = exc.amount_impact or Decimal(0)
        unreconciled_amount += amount
        if exc.exception_type != "MISSING_EXTERNAL_RECORD":
            continue
        txn = db.get(Transaction, exc.transaction_id)
        if txn is None:
            continue
        if txn.debit_credit == "CREDIT":
            expected_inflows += amount
        else:
            expected_outflows += amount

    position = CashPosition(
        client_id=client_id, batch_id=as_of_batch.id, as_of=date_.today(),
        confirmed_cash=confirmed_cash, pending_cash=pending_cash,
        expected_inflows=expected_inflows, expected_outflows=expected_outflows,
        unreconciled_amount=unreconciled_amount,
        detail={
            "batches_considered": client_batches,
            "open_exception_count": len(open_exceptions),
            "unexplained_settlement_count": len(unexplained_settlements),
            "by_bank_account": {k: str(v) for k, v in by_account.items()},
            "internal_transfer_volume": str(internal_transfer_volume),
            "internal_transfer_note": (
                "Movements between the client's own accounts are reconciled and shown per account, "
                "but deliberately excluded from confirmed_cash -- they redistribute cash rather "
                "than change the total."
            ),
        },
    )
    db.add(position)
    db.flush()
    return position
