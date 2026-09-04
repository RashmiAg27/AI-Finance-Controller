from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.cash import CashForecast, CashPosition
from app.schemas.cash import CashForecastResponse, CashPositionResponse

router = APIRouter(tags=["cash"])


@router.get("/clients/{client_id}/cash-position", response_model=CashPositionResponse)
def get_latest_cash_position(client_id: str, db: Session = Depends(get_db)):
    position = db.execute(
        select(CashPosition).where(CashPosition.client_id == client_id).order_by(CashPosition.created_at.desc())
    ).scalars().first()
    if position is None:
        raise HTTPException(status_code=404, detail=f"No cash position computed yet for client {client_id}")
    return position


@router.get("/clients/{client_id}/cash-forecast", response_model=CashForecastResponse)
def get_latest_cash_forecast(client_id: str, db: Session = Depends(get_db)):
    forecast = db.execute(
        select(CashForecast).where(CashForecast.client_id == client_id).order_by(CashForecast.created_at.desc())
    ).scalars().first()
    if forecast is None:
        raise HTTPException(status_code=404, detail=f"No cash forecast computed yet for client {client_id}")
    return forecast
