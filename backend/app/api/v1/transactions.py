from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.transaction import Transaction, TransactionIdentifier
from app.schemas.transaction import TransactionIdentifierResponse, TransactionResponse

router = APIRouter(tags=["transactions"])


def _to_response(db: Session, txn: Transaction) -> TransactionResponse:
    identifiers = list(
        db.execute(select(TransactionIdentifier).where(TransactionIdentifier.transaction_id == txn.id)).scalars()
    )
    data = TransactionResponse.model_validate(txn).model_dump()
    data["identifiers"] = [TransactionIdentifierResponse.model_validate(i) for i in identifiers]
    return TransactionResponse.model_validate(data)


@router.get("/batches/{batch_id}/transactions", response_model=list[TransactionResponse])
def list_batch_transactions(batch_id: str, source_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Transaction).where(Transaction.batch_id == batch_id)
    if source_id:
        stmt = stmt.where(Transaction.source_id == source_id)
    stmt = stmt.order_by(Transaction.transaction_date, Transaction.id)
    txns = list(db.execute(stmt).scalars())
    return [_to_response(db, t) for t in txns]


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {transaction_id}")
    return _to_response(db, txn)
