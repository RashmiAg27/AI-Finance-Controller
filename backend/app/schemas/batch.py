from datetime import datetime

from pydantic import BaseModel


class BatchCreateRequest(BaseModel):
    batch_code: str


class BatchResponse(BaseModel):
    id: str
    client_id: str
    batch_code: str
    config_version_id: str
    status: str
    batch_definition_id: str | None = None
    business_date: str | None = None
    triggered_by_type: str | None = None
    triggered_by: str | None = None
    current_stage: str | None = None
    progress_pct: int = 0
    created_at: datetime
    files_received_at: datetime | None = None
    validated_at: datetime | None = None
    normalized_at: datetime | None = None
    reconciliation_started_at: datetime | None = None
    reconciliation_completed_at: datetime | None = None
    exceptions_identified_at: datetime | None = None
    exceptions_resolved_at: datetime | None = None
    tax_processing_at: datetime | None = None
    settlement_processing_at: datetime | None = None
    reporting_at: datetime | None = None
    closed_at: datetime | None = None
    failure_reason: str | None = None

    model_config = {"from_attributes": True}
