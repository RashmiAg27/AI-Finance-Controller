from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.data_source import DataSource
from app.models.transaction import Transaction, TransactionIdentifier
from app.schemas.config import ClientConfigSchema


@dataclass
class TxnView:
    """Lightweight in-memory projection of a Transaction used by the matching
    engine, so passes don't repeatedly hit the DB per comparison."""

    id: str
    canonical_reference: str | None
    amount: Decimal
    transaction_date: date
    value_date: date | None
    settlement_date: date | None
    counterparty: str | None
    description: str | None
    instrument_type: str
    source_id: str
    identifiers: dict[str, str] = field(default_factory=dict)  # identifier_type -> value_normalized

    def date_for(self, field_name: str) -> date | None:
        return getattr(self, field_name)


def load_transaction_views(db: Session, batch: Batch, config: ClientConfigSchema) -> tuple[list[TxnView], list[TxnView]]:
    """Returns (internal_pool, external_pool) sorted by (transaction_date, id)
    for determinism -- reconciliation must be reproducible given the same
    inputs and config version."""
    role_by_source_id = {ds.source_id: ds.role for ds in config.data_sources}

    txns = list(
        db.execute(
            select(Transaction)
            .where(Transaction.batch_id == batch.id)
            .order_by(Transaction.transaction_date, Transaction.id)
        ).scalars()
    )
    identifiers = list(
        db.execute(
            select(TransactionIdentifier).where(TransactionIdentifier.transaction_id.in_([t.id for t in txns]))
        ).scalars()
    ) if txns else []
    identifiers_by_txn: dict[str, dict[str, str]] = {}
    for ident in identifiers:
        identifiers_by_txn.setdefault(ident.transaction_id, {})[ident.identifier_type] = ident.value_normalized

    internal_pool: list[TxnView] = []
    external_pool: list[TxnView] = []
    for txn in txns:
        view = TxnView(
            id=txn.id,
            canonical_reference=txn.canonical_reference,
            amount=txn.amount,
            transaction_date=txn.transaction_date,
            value_date=txn.value_date,
            settlement_date=txn.settlement_date,
            counterparty=txn.counterparty,
            description=txn.description,
            instrument_type=txn.instrument_type,
            source_id=txn.source_id,
            identifiers=identifiers_by_txn.get(txn.id, {}),
        )
        role = role_by_source_id.get(txn.source_id)
        if role == "INTERNAL":
            internal_pool.append(view)
        elif role == "EXTERNAL":
            external_pool.append(view)
    return internal_pool, external_pool
