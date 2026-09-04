"""Request/response contracts for the four operator windows: Reconciliation
Management, Tax & Fees, Matching Rules, and Forecast."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Import sources
# ---------------------------------------------------------------------------

class ImportSourceResponse(BaseModel):
    id: str
    client_id: str
    code: str
    name: str
    kind: str
    connection_json: dict = Field(default_factory=dict)
    enabled: bool
    location: str | None = None
    last_polled_at: datetime | None = None
    last_status: str | None = None
    last_message: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None

    model_config = {"from_attributes": True}


class ImportSourceCreateRequest(BaseModel):
    code: str
    name: str
    kind: Literal["LOCAL_DIRECTORY", "EMAIL_INBOX", "SFTP_CONNECTION", "API_CONNECTION"]
    connection_json: dict = Field(default_factory=dict)
    enabled: bool = True


class ImportSourceUpdateRequest(BaseModel):
    """Every field optional: the Edit dialog sends only what changed, and a
    field that is absent must keep its stored value rather than being reset."""

    name: str | None = None
    kind: Literal["LOCAL_DIRECTORY", "EMAIL_INBOX", "SFTP_CONNECTION", "API_CONNECTION"] | None = None
    connection_json: dict | None = None
    enabled: bool | None = None

    def to_patch(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ImportProbeResponse(BaseModel):
    kind: str
    location: str
    status: str
    files: list[dict]
    log: list[str]


# ---------------------------------------------------------------------------
# Bank accounts -- the reconciliation units
# ---------------------------------------------------------------------------

class BankAccountResponse(BaseModel):
    id: str
    client_id: str
    account_code: str
    display_name: str
    bank_name: str
    account_number_masked: str
    ifsc: str | None = None
    branch: str | None = None
    account_type: str
    purpose: str
    currency: str
    gl_code: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class BankAccountCreateRequest(BaseModel):
    account_code: str
    display_name: str
    bank_name: str
    account_number_masked: str
    ifsc: str | None = None
    branch: str | None = None
    account_type: str = "CURRENT"
    purpose: str = "OPERATING"
    currency: str = "INR"
    gl_code: str | None = None


class BankAccountUpdateRequest(BaseModel):
    display_name: str | None = None
    bank_name: str | None = None
    account_number_masked: str | None = None
    ifsc: str | None = None
    branch: str | None = None
    account_type: str | None = None
    purpose: str | None = None
    currency: str | None = None
    gl_code: str | None = None
    is_active: bool | None = None

    def to_patch(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


# ---------------------------------------------------------------------------
# Batch definitions
# ---------------------------------------------------------------------------

class BatchRunSummary(BaseModel):
    id: str
    batch_code: str
    status: str
    current_stage: str | None = None
    progress_pct: int = 0
    business_date: str | None = None
    triggered_by_type: str | None = None
    triggered_by: str | None = None
    created_at: datetime | None = None
    closed_at: datetime | None = None
    failure_reason: str | None = None

    model_config = {"from_attributes": True}


class BatchDefinitionResponse(BaseModel):
    id: str
    client_id: str
    code: str
    name: str
    description: str | None = None
    batch_type: str
    reconciliation_type: str
    reconciliation_label: str | None = None
    bank_account_id: str | None = None
    bank_account_label: str | None = None
    trigger_type: str
    trigger_detail: str | None = None
    import_source_id: str | None = None
    import_source_code: str | None = None
    import_source_kind: str | None = None
    import_location: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    enabled: bool
    cutoff_time: str | None = None
    sla_minutes: int = 60
    owner_team: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None

    # Derived, never stored -- see domains.batches.definitions.definition_state
    state: str
    data_available: bool | None = None
    available_source_ids: list[str] = Field(default_factory=list)
    missing_source_ids: list[str] = Field(default_factory=list)
    latest_run: BatchRunSummary | None = None


class BatchDefinitionCreateRequest(BaseModel):
    code: str
    name: str
    source_ids: list[str]
    import_source_id: str | None = None
    reconciliation_type: str = "BANK_GL"
    bank_account_id: str | None = None
    batch_type: str = "DAILY_STATEMENT"
    trigger_type: str = "MANUAL"
    trigger_detail: str | None = None
    description: str | None = None
    cutoff_time: str | None = None
    sla_minutes: int = 60
    owner_team: str | None = None
    enabled: bool = True


class BatchDefinitionUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    batch_type: str | None = None
    reconciliation_type: str | None = None
    bank_account_id: str | None = None
    trigger_type: str | None = None
    trigger_detail: str | None = None
    import_source_id: str | None = None
    source_ids: list[str] | None = None
    enabled: bool | None = None
    cutoff_time: str | None = None
    sla_minutes: int | None = None
    owner_team: str | None = None

    def to_patch(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class RunRequest(BaseModel):
    actor: str = "operator"
    triggered_by_type: str = "MANUAL"
    business_date: str | None = None


class RunAllRequest(BaseModel):
    actor: str = "operator"
    triggered_by_type: str = "MANUAL"
    business_date: str | None = None
    batch_definition_ids: list[str] | None = None  # None = every enabled definition


class RunAcceptedResponse(BaseModel):
    queued: list[BatchRunSummary]
    skipped: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Batch log
# ---------------------------------------------------------------------------

class BatchLogEntryResponse(BaseModel):
    seq: int
    created_at: datetime
    level: str
    stage: str
    message: str
    detail_json: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Configuration windows
# ---------------------------------------------------------------------------

class ConfigSectionUpdateRequest(BaseModel):
    """A whole-section replacement. The UI edits a section, sends it back, and
    the server versions and activates it -- there is no partial field patch,
    because a half-applied matching rule is not a valid configuration."""

    sections: dict[str, Any]
    actor: str = "operator"


class ConfigSectionResponse(BaseModel):
    client_id: str
    config_version: int
    data: dict
