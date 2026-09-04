from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.exception_ import Exception_, ExceptionEvidence, ExceptionTransaction
from app.schemas.exception_ import ExceptionEvidenceResponse, ExceptionResponse, ExceptionTransactionRef

router = APIRouter(tags=["exceptions"])


def _to_response(db: Session, exc: Exception_) -> ExceptionResponse:
    txns = list(
        db.execute(select(ExceptionTransaction).where(ExceptionTransaction.exception_id == exc.id)).scalars()
    )
    evidence = list(
        db.execute(select(ExceptionEvidence).where(ExceptionEvidence.exception_id == exc.id)).scalars()
    )
    data = ExceptionResponse.model_validate(exc).model_dump()
    data["transactions"] = [ExceptionTransactionRef.model_validate(t) for t in txns]
    data["evidence"] = [ExceptionEvidenceResponse.model_validate(e) for e in evidence]
    return ExceptionResponse.model_validate(data)


@router.get("/batches/{batch_id}/exceptions", response_model=list[ExceptionResponse])
def list_batch_exceptions(
    batch_id: str, exception_type: str | None = None, status: str | None = None,
    severity: str | None = None, db: Session = Depends(get_db),
):
    stmt = select(Exception_).where(Exception_.batch_id == batch_id)
    if exception_type:
        stmt = stmt.where(Exception_.exception_type == exception_type)
    if status:
        stmt = stmt.where(Exception_.status == status)
    if severity:
        stmt = stmt.where(Exception_.severity == severity)
    stmt = stmt.order_by(Exception_.created_at)
    exceptions = list(db.execute(stmt).scalars())
    return [_to_response(db, e) for e in exceptions]


@router.get("/exceptions/{exception_id}", response_model=ExceptionResponse)
def get_exception(exception_id: str, db: Session = Depends(get_db)):
    exc = db.get(Exception_, exception_id)
    if exc is None:
        raise HTTPException(status_code=404, detail=f"Exception not found: {exception_id}")
    return _to_response(db, exc)
