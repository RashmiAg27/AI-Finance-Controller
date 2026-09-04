from datetime import datetime

from pydantic import BaseModel


class ReconciliationRunResponse(BaseModel):
    id: str
    batch_id: str
    run_number: int
    config_version_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    stats_json: dict

    model_config = {"from_attributes": True}


class MatchEvidenceResponse(BaseModel):
    evidence_type: str
    field_name: str
    source_value: str | None
    target_value: str | None
    comparator: str
    passed: bool
    detail_json: dict

    model_config = {"from_attributes": True}


class MatchTransactionRef(BaseModel):
    transaction_id: str
    side: str

    model_config = {"from_attributes": True}


class ReconciliationMatchResponse(BaseModel):
    id: str
    reconciliation_run_id: str
    match_type: str
    cardinality: str
    rule_id: str
    rule_version: int
    confidence: float
    status: str
    created_at: datetime
    transactions: list[MatchTransactionRef] = []
    evidence: list[MatchEvidenceResponse] = []

    model_config = {"from_attributes": True}
