from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.reconciliation import MatchEvidence, ReconciliationMatch, ReconciliationMatchTransaction, ReconciliationRun
from app.schemas.reconciliation import (
    MatchEvidenceResponse,
    MatchTransactionRef,
    ReconciliationMatchResponse,
    ReconciliationRunResponse,
)

router = APIRouter(tags=["reconciliation"])


def _to_match_response(db: Session, match: ReconciliationMatch) -> ReconciliationMatchResponse:
    txns = list(
        db.execute(
            select(ReconciliationMatchTransaction).where(ReconciliationMatchTransaction.match_id == match.id)
        ).scalars()
    )
    evidence = list(db.execute(select(MatchEvidence).where(MatchEvidence.match_id == match.id)).scalars())
    data = ReconciliationMatchResponse.model_validate(match).model_dump()
    data["transactions"] = [MatchTransactionRef.model_validate(t) for t in txns]
    data["evidence"] = [MatchEvidenceResponse.model_validate(e) for e in evidence]
    return ReconciliationMatchResponse.model_validate(data)


@router.get("/batches/{batch_id}/reconciliation-runs", response_model=list[ReconciliationRunResponse])
def list_reconciliation_runs(batch_id: str, db: Session = Depends(get_db)):
    stmt = select(ReconciliationRun).where(ReconciliationRun.batch_id == batch_id).order_by(ReconciliationRun.run_number)
    return list(db.execute(stmt).scalars())


@router.get("/batches/{batch_id}/matches", response_model=list[ReconciliationMatchResponse])
def list_batch_matches(batch_id: str, db: Session = Depends(get_db)):
    run_ids = list(
        db.execute(select(ReconciliationRun.id).where(ReconciliationRun.batch_id == batch_id)).scalars()
    )
    if not run_ids:
        return []
    matches = list(
        db.execute(
            select(ReconciliationMatch)
            .where(ReconciliationMatch.reconciliation_run_id.in_(run_ids))
            .order_by(ReconciliationMatch.created_at)
        ).scalars()
    )
    return [_to_match_response(db, m) for m in matches]


@router.get("/matches/{match_id}", response_model=ReconciliationMatchResponse)
def get_match(match_id: str, db: Session = Depends(get_db)):
    match = db.get(ReconciliationMatch, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Match not found: {match_id}")
    return _to_match_response(db, match)
