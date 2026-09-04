from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class CashPositionResponse(BaseModel):
    id: str
    client_id: str
    batch_id: str
    as_of: date
    confirmed_cash: Decimal
    pending_cash: Decimal
    expected_inflows: Decimal
    expected_outflows: Decimal
    unreconciled_amount: Decimal
    detail: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class CashForecastResponse(BaseModel):
    id: str
    client_id: str
    cash_position_id: str
    horizon_days: int
    as_of: date
    expected_value: Decimal
    low_estimate: Decimal
    high_estimate: Decimal
    drivers: dict
    assumptions_note: str
    created_at: datetime

    model_config = {"from_attributes": True}
