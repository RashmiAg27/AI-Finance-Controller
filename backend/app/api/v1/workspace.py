"""Endpoints behind the four operator windows.

Reconciliation Management edits batch definitions and import sources and runs
them; Tax & Fees and Matching Rules edit versioned configuration sections;
Forecast reads the cash projection. Every mutation goes through a domain
service so the audit trail and config versioning happen in one place.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ConfigValidationError, ConfigVersionError, DomainError, NotFoundError
from app.domains.batches import definitions as definitions_service
from app.domains.batches import run_log, runner
from app.domains.batches import service as batch_service
from app.domains.clients import accounts as accounts_service, config_editor
from app.domains.reconciliation import types as recon_types
from app.models.bank_account import BankAccount
from app.domains.ingestion import import_sources as import_sources_domain
from app.models.client import Client
from app.models.import_source import ImportSource
from app.schemas.workspace import (
    BankAccountCreateRequest,
    BankAccountResponse,
    BankAccountUpdateRequest,
    BatchDefinitionCreateRequest,
    BatchDefinitionResponse,
    BatchDefinitionUpdateRequest,
    BatchLogEntryResponse,
    BatchRunSummary,
    ConfigSectionResponse,
    ConfigSectionUpdateRequest,
    ImportProbeResponse,
    ImportSourceCreateRequest,
    ImportSourceResponse,
    ImportSourceUpdateRequest,
    RunAcceptedResponse,
    RunAllRequest,
    RunRequest,
)

router = APIRouter(tags=["workspace"])


def _http(exc: DomainError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ConfigValidationError, ConfigVersionError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _client_code(db: Session, client_id: str) -> str:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail=f"no client {client_id!r}")
    return client.code


# ---------------------------------------------------------------------------
# Import sources
# ---------------------------------------------------------------------------

def _import_source_response(row: ImportSource, client_code: str) -> ImportSourceResponse:
    response = ImportSourceResponse.model_validate(row)
    response.location = import_sources_domain.describe_location(row, client_code)
    return response


@router.get("/clients/{client_id}/import-sources", response_model=list[ImportSourceResponse])
def list_import_sources(client_id: str, db: Session = Depends(get_db)):
    code = _client_code(db, client_id)
    return [_import_source_response(row, code)
            for row in definitions_service.list_import_sources(db, client_id)]


@router.post("/clients/{client_id}/import-sources", response_model=ImportSourceResponse)
def create_import_source(client_id: str, payload: ImportSourceCreateRequest, db: Session = Depends(get_db)):
    try:
        row = definitions_service.create_import_source(
            db, client_id=client_id, code=payload.code, name=payload.name, kind=payload.kind,
            connection=payload.connection_json, enabled=payload.enabled,
        )
        db.commit()
        return _import_source_response(row, _client_code(db, client_id))
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


@router.patch("/import-sources/{import_source_id}", response_model=ImportSourceResponse)
def update_import_source(import_source_id: str, payload: ImportSourceUpdateRequest,
                         db: Session = Depends(get_db)):
    try:
        row = definitions_service.update_import_source(db, import_source_id, payload.to_patch(), actor="operator")
        db.commit()
        return _import_source_response(row, _client_code(db, row.client_id))
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


@router.post("/import-sources/{import_source_id}/probe", response_model=ImportProbeResponse)
def probe_import_source(import_source_id: str, db: Session = Depends(get_db)):
    try:
        result = definitions_service.probe_import_source(db, import_source_id)
        db.commit()
        return result
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


# ---------------------------------------------------------------------------
# Bank accounts -- the reconciliation units
# ---------------------------------------------------------------------------

@router.get("/clients/{client_id}/bank-accounts", response_model=list[BankAccountResponse])
def list_bank_accounts(client_id: str, active_only: bool = False, db: Session = Depends(get_db)):
    return accounts_service.list_accounts(db, client_id, active_only=active_only)


@router.post("/clients/{client_id}/bank-accounts", response_model=BankAccountResponse)
def create_bank_account(client_id: str, payload: BankAccountCreateRequest, db: Session = Depends(get_db)):
    try:
        row = accounts_service.create_account(db, client_id=client_id, **payload.model_dump())
        db.commit()
        return row
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


@router.patch("/bank-accounts/{account_id}", response_model=BankAccountResponse)
def update_bank_account(account_id: str, payload: BankAccountUpdateRequest, db: Session = Depends(get_db)):
    try:
        row = accounts_service.update_account(db, account_id, payload.to_patch(), actor="operator")
        db.commit()
        return row
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


@router.get("/reconciliation-types")
def list_reconciliation_types():
    """The catalogue of proofs this platform performs, each with the sides it
    compares, its natural key, and which differences are legitimate. The UI
    groups the Reconciliation window by these, and the agent uses the same
    descriptions when explaining why a difference is or is not a break."""
    return recon_types.catalogue()


# ---------------------------------------------------------------------------
# Batch definitions
# ---------------------------------------------------------------------------

def _definition_response(db: Session, definition, *, check_data: bool = True) -> BatchDefinitionResponse:
    state = definitions_service.definition_state(db, definition, check_data=check_data)
    import_source = db.get(ImportSource, definition.import_source_id) if definition.import_source_id else None
    account = db.get(BankAccount, definition.bank_account_id) if definition.bank_account_id else None
    latest = state["latest_batch"]
    return BatchDefinitionResponse(
        id=definition.id, client_id=definition.client_id, code=definition.code, name=definition.name,
        description=definition.description, batch_type=definition.batch_type,
        reconciliation_type=definition.reconciliation_type,
        reconciliation_label=recon_types.describe(definition.reconciliation_type)["label"],
        bank_account_id=definition.bank_account_id,
        bank_account_label=f"{account.bank_name} {account.account_number_masked}" if account else None,
        trigger_type=definition.trigger_type, trigger_detail=definition.trigger_detail,
        import_source_id=definition.import_source_id,
        import_source_code=import_source.code if import_source else None,
        import_source_kind=import_source.kind if import_source else None,
        import_location=state["import_location"],
        source_ids=list(definition.source_ids or []), enabled=definition.enabled,
        cutoff_time=definition.cutoff_time, sla_minutes=definition.sla_minutes,
        owner_team=definition.owner_team, updated_at=definition.updated_at, updated_by=definition.updated_by,
        state=state["state"], data_available=state["data_available"],
        available_source_ids=state["available_source_ids"], missing_source_ids=state["missing_source_ids"],
        latest_run=BatchRunSummary.model_validate(latest) if latest is not None else None,
    )


@router.get("/clients/{client_id}/batch-definitions", response_model=list[BatchDefinitionResponse])
def list_batch_definitions(client_id: str, check_data: bool = True, db: Session = Depends(get_db)):
    return [_definition_response(db, d, check_data=check_data)
            for d in definitions_service.list_definitions(db, client_id)]


@router.get("/batch-definitions/{definition_id}", response_model=BatchDefinitionResponse)
def get_batch_definition(definition_id: str, db: Session = Depends(get_db)):
    try:
        return _definition_response(db, definitions_service.get_definition(db, definition_id))
    except DomainError as exc:
        raise _http(exc)


@router.post("/clients/{client_id}/batch-definitions", response_model=BatchDefinitionResponse)
def create_batch_definition(client_id: str, payload: BatchDefinitionCreateRequest, db: Session = Depends(get_db)):
    try:
        row = definitions_service.create_definition(db, client_id=client_id, **payload.model_dump())
        db.commit()
        return _definition_response(db, row)
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


@router.patch("/batch-definitions/{definition_id}", response_model=BatchDefinitionResponse)
def update_batch_definition(definition_id: str, payload: BatchDefinitionUpdateRequest,
                            db: Session = Depends(get_db)):
    try:
        row = definitions_service.update_definition(db, definition_id, payload.to_patch(), actor="operator")
        db.commit()
        return _definition_response(db, row)
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

def _queue(db: Session, definition, *, actor: str, triggered_by_type: str,
           business_date: str | None) -> BatchRunSummary:
    """Creates the Batch row, commits it, then hands the id to the runner --
    the worker thread has its own session and must not race a transaction that
    has not landed yet."""
    business_date = business_date or definitions_service.next_business_date(db, definition)
    batch = batch_service.create_batch(
        db, client_id=definition.client_id,
        batch_code=definitions_service.next_batch_code(db, definition, business_date),
        actor=actor, batch_definition_id=definition.id, business_date=business_date,
        triggered_by_type=triggered_by_type,
    )
    db.commit()
    runner.submit(batch.id)
    return BatchRunSummary.model_validate(batch)


@router.post("/batch-definitions/{definition_id}/run", response_model=RunAcceptedResponse)
def run_batch_definition(definition_id: str, payload: RunRequest, db: Session = Depends(get_db)):
    try:
        definition = definitions_service.get_definition(db, definition_id)
        if not definition.enabled:
            return RunAcceptedResponse(queued=[], skipped=[
                {"batch_definition_id": definition.id, "code": definition.code,
                 "reason": "definition is disabled"}])
        summary = _queue(db, definition, actor=payload.actor,
                         triggered_by_type=payload.triggered_by_type, business_date=payload.business_date)
        return RunAcceptedResponse(queued=[summary])
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


@router.post("/clients/{client_id}/batch-definitions/run", response_model=RunAcceptedResponse)
def run_batch_definitions(client_id: str, payload: RunAllRequest, db: Session = Depends(get_db)):
    """Run-all, or run-a-named-subset. Definitions that cannot run are
    reported in `skipped` with a reason rather than failing the whole
    request -- one disabled batch must not stop the other five."""
    definitions = definitions_service.list_definitions(db, client_id)
    if payload.batch_definition_ids is not None:
        wanted = set(payload.batch_definition_ids)
        definitions = [d for d in definitions if d.id in wanted or d.code in wanted]

    queued, skipped = [], []
    for definition in definitions:
        if not definition.enabled:
            skipped.append({"batch_definition_id": definition.id, "code": definition.code,
                            "reason": "definition is disabled"})
            continue
        try:
            queued.append(_queue(db, definition, actor=payload.actor,
                                 triggered_by_type=payload.triggered_by_type,
                                 business_date=payload.business_date))
        except DomainError as exc:
            db.rollback()
            skipped.append({"batch_definition_id": definition.id, "code": definition.code, "reason": str(exc)})
    return RunAcceptedResponse(queued=queued, skipped=skipped)


# ---------------------------------------------------------------------------
# Batch log
# ---------------------------------------------------------------------------

@router.get("/batches/{batch_id}/logs", response_model=list[BatchLogEntryResponse])
def get_batch_logs(batch_id: str, since_seq: int = 0, db: Session = Depends(get_db)):
    return run_log.entries(db, batch_id, since_seq=since_seq)


# ---------------------------------------------------------------------------
# Configuration windows
# ---------------------------------------------------------------------------

@router.get("/clients/{client_id}/tax-config", response_model=ConfigSectionResponse)
def get_tax_config(client_id: str, db: Session = Depends(get_db)):
    try:
        view = config_editor.tax_view(db, client_id)
        return ConfigSectionResponse(client_id=client_id, config_version=view["config_version"], data=view)
    except DomainError as exc:
        raise _http(exc)


@router.put("/clients/{client_id}/tax-config", response_model=ConfigSectionResponse)
def put_tax_config(client_id: str, payload: ConfigSectionUpdateRequest, db: Session = Depends(get_db)):
    try:
        row = config_editor.patch_active_config(db, client_id, payload.sections, actor=payload.actor)
        db.commit()
        view = config_editor.tax_view(db, client_id)
        return ConfigSectionResponse(client_id=client_id, config_version=row.version, data=view)
    except DomainError as exc:
        db.rollback()
        raise _http(exc)


@router.get("/clients/{client_id}/matching-config", response_model=ConfigSectionResponse)
def get_matching_config(client_id: str, db: Session = Depends(get_db)):
    try:
        view = config_editor.matching_view(db, client_id)
        return ConfigSectionResponse(client_id=client_id, config_version=view["config_version"], data=view)
    except DomainError as exc:
        raise _http(exc)


@router.put("/clients/{client_id}/matching-config", response_model=ConfigSectionResponse)
def put_matching_config(client_id: str, payload: ConfigSectionUpdateRequest, db: Session = Depends(get_db)):
    try:
        row = config_editor.patch_active_config(db, client_id, payload.sections, actor=payload.actor)
        db.commit()
        view = config_editor.matching_view(db, client_id)
        return ConfigSectionResponse(client_id=client_id, config_version=row.version, data=view)
    except DomainError as exc:
        db.rollback()
        raise _http(exc)
