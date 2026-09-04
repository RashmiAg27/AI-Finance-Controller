from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.settlement import Settlement, SettlementComponent
from app.schemas.settlement import SettlementComponentResponse, SettlementResponse

router = APIRouter(tags=["settlements"])


def _to_response(db: Session, settlement: Settlement) -> SettlementResponse:
    components = list(
        db.execute(select(SettlementComponent).where(SettlementComponent.settlement_id == settlement.id)).scalars()
    )
    data = SettlementResponse.model_validate(settlement).model_dump()
    data["components"] = [SettlementComponentResponse.model_validate(c) for c in components]
    return SettlementResponse.model_validate(data)


@router.get("/batches/{batch_id}/settlements", response_model=list[SettlementResponse])
def list_batch_settlements(batch_id: str, db: Session = Depends(get_db)):
    settlements = list(db.execute(select(Settlement).where(Settlement.batch_id == batch_id)).scalars())
    return [_to_response(db, s) for s in settlements]


@router.get("/settlements/{settlement_id}", response_model=SettlementResponse)
def get_settlement(settlement_id: str, db: Session = Depends(get_db)):
    settlement = db.get(Settlement, settlement_id)
    if settlement is None:
        raise HTTPException(status_code=404, detail=f"Settlement not found: {settlement_id}")
    return _to_response(db, settlement)
