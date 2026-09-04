from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class SettlementComponentResponse(BaseModel):
    component_type: str
    amount: Decimal
    description: str
    tax_rule_id: str | None

    model_config = {"from_attributes": True}


class SettlementResponse(BaseModel):
    id: str
    batch_id: str
    reconciliation_match_id: str
    gross_amount: Decimal
    net_amount_expected: Decimal
    net_amount_observed: Decimal
    is_fully_explained: bool
    detail: dict
    created_at: datetime
    components: list[SettlementComponentResponse] = []

    model_config = {"from_attributes": True}
