from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ExceptionEvidenceResponse(BaseModel):
    evidence_type: str
    field_name: str
    value_observed: str | None
    comparator: str | None
    detail_json: dict

    model_config = {"from_attributes": True}


class ExceptionTransactionRef(BaseModel):
    transaction_id: str
    role: str

    model_config = {"from_attributes": True}


class ExceptionResponse(BaseModel):
    id: str
    batch_id: str
    transaction_id: str
    exception_type: str
    severity: str
    status: str
    amount_impact: Decimal | None
    likely_cause: str | None
    confidence: float | None
    recommended_action: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    resolved_at: datetime | None
    resolution: str | None
    resolved_by: str | None
    transactions: list[ExceptionTransactionRef] = []
    evidence: list[ExceptionEvidenceResponse] = []

    model_config = {"from_attributes": True}
