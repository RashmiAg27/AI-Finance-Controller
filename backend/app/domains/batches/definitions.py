"""Configured batches and the import sources that feed them.

This is the layer the Reconciliation window edits: a BatchDefinition is the
standing instruction, an ImportSource is where its files come from, and a
Batch is one execution of the pair. Editing either is a normal, audited
operator action -- it never mutates a run already in flight, because a Batch
binds its config_version_id when it is created.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_event
from app.core.clock import default_clock
from app.core.errors import DomainError, NotFoundError
from app.core.timezone import to_display_timezone
from app.domains.batches import state_machine
from app.domains.ingestion import import_sources as import_sources_domain
from app.domains.reconciliation import types as recon_types
from app.models.bank_account import BankAccount
from app.models.batch import Batch
from app.models.batch_definition import BATCH_TYPES, TRIGGER_TYPES, BatchDefinition
from app.models.client import Client
from app.models.data_source import DataSource
from app.models.import_source import IMPORT_SOURCE_KINDS, ImportSource

# What the Reconciliation blotter shows in the "State" column. Derived on read
# from the definition's latest Batch plus what its import source currently
# holds -- never stored, so it can't drift from reality.
STATE_DISABLED = "DISABLED"
STATE_AWAITING_DATA = "AWAITING_DATA"
STATE_DATA_AVAILABLE = "DATA_AVAILABLE"
STATE_RUNNING = "RUNNING"
STATE_COMPLETED = "COMPLETED"
STATE_FAILED = "FAILED"

_RUNNING_STATUSES = {
    state_machine.CREATED, state_machine.FILES_RECEIVED, state_machine.VALIDATED,
    state_machine.NORMALIZED, state_machine.RECONCILIATION_RUNNING,
    state_machine.RECONCILIATION_COMPLETED, state_machine.EXCEPTIONS_IDENTIFIED,
    state_machine.EXCEPTIONS_RESOLVED, state_machine.TAX_PROCESSING,
    state_machine.SETTLEMENT_PROCESSING, state_machine.REPORTING,
}

_EDITABLE_DEFINITION_FIELDS = {
    "name", "description", "batch_type", "reconciliation_type", "bank_account_id",
    "trigger_type", "trigger_detail",
    "import_source_id", "source_ids", "enabled", "cutoff_time", "sla_minutes", "owner_team",
}
_EDITABLE_IMPORT_SOURCE_FIELDS = {"name", "kind", "connection_json", "enabled"}


# ---------------------------------------------------------------------------
# Import sources
# ---------------------------------------------------------------------------

def list_import_sources(db: Session, client_id: str) -> list[ImportSource]:
    return list(db.execute(
        select(ImportSource).where(ImportSource.client_id == client_id).order_by(ImportSource.code)
    ).scalars())


def get_import_source(db: Session, import_source_id: str) -> ImportSource:
    row = db.get(ImportSource, import_source_id)
    if row is None:
        raise NotFoundError("ImportSource", import_source_id)
    return row


def create_import_source(db: Session, *, client_id: str, code: str, name: str, kind: str,
                         connection: dict, enabled: bool = True, actor: str = "system") -> ImportSource:
    if kind not in IMPORT_SOURCE_KINDS:
        raise DomainError(f"unknown import source kind {kind!r}; expected one of {list(IMPORT_SOURCE_KINDS)}")
    import_sources_domain.validate_connection(kind, connection)
    row = ImportSource(client_id=client_id, code=code, name=name, kind=kind,
                       connection_json=connection, enabled=enabled, updated_by=actor)
    db.add(row)
    db.flush()
    record_event(db, entity_type="IMPORT_SOURCE", entity_id=row.id, event_type="IMPORT_SOURCE_CREATED",
                 payload={"client_id": client_id, "code": code, "kind": kind}, actor=actor)
    return row


def update_import_source(db: Session, import_source_id: str, patch: dict[str, Any],
                         *, actor: str = "system") -> ImportSource:
    row = get_import_source(db, import_source_id)
    unknown = sorted(set(patch) - _EDITABLE_IMPORT_SOURCE_FIELDS)
    if unknown:
        raise DomainError(f"cannot edit field(s) {unknown} on an import source; "
                          f"editable: {sorted(_EDITABLE_IMPORT_SOURCE_FIELDS)}")

    before = {"kind": row.kind, "connection_json": dict(row.connection_json or {}), "enabled": row.enabled}
    kind = patch.get("kind", row.kind)
    if kind not in IMPORT_SOURCE_KINDS:
        raise DomainError(f"unknown import source kind {kind!r}")
    connection = patch.get("connection_json", row.connection_json) or {}
    import_sources_domain.validate_connection(kind, connection)

    for field, value in patch.items():
        setattr(row, field, value)
    row.updated_by = actor
    # A saved edit invalidates the previous poll result -- the operator must
    # not read a stale "OK" from the old directory as proof the new one works.
    row.last_polled_at = None
    row.last_status = None
    row.last_message = None
    db.flush()
    record_event(db, entity_type="IMPORT_SOURCE", entity_id=row.id, event_type="IMPORT_SOURCE_UPDATED",
                 payload={"before": before, "after": {"kind": row.kind,
                                                       "connection_json": dict(row.connection_json or {}),
                                                       "enabled": row.enabled}}, actor=actor)
    return row


def probe_import_source(db: Session, import_source_id: str) -> dict:
    row = get_import_source(db, import_source_id)
    client = db.get(Client, row.client_id)
    result = import_sources_domain.probe(row, client_code=client.code)
    row.last_polled_at = default_clock.now()
    row.last_status = result["status"]
    row.last_message = f"{len(result['files'])} file(s) at {result['location']}"
    db.flush()
    return result


# ---------------------------------------------------------------------------
# Batch definitions
# ---------------------------------------------------------------------------

def list_definitions(db: Session, client_id: str) -> list[BatchDefinition]:
    return list(db.execute(
        select(BatchDefinition).where(BatchDefinition.client_id == client_id).order_by(BatchDefinition.code)
    ).scalars())


def get_definition(db: Session, definition_id: str) -> BatchDefinition:
    row = db.get(BatchDefinition, definition_id)
    if row is None:
        raise NotFoundError("BatchDefinition", definition_id)
    return row


def create_definition(db: Session, *, client_id: str, code: str, name: str, source_ids: list[str],
                      import_source_id: str | None = None, batch_type: str = "DAILY_STATEMENT",
                      reconciliation_type: str = "BANK_GL", bank_account_id: str | None = None,
                      trigger_type: str = "MANUAL", trigger_detail: str | None = None,
                      description: str | None = None, cutoff_time: str | None = None,
                      sla_minutes: int = 60, owner_team: str | None = None,
                      enabled: bool = True, actor: str = "system") -> BatchDefinition:
    _validate_definition_fields(db, client_id, batch_type=batch_type, trigger_type=trigger_type,
                                source_ids=source_ids, import_source_id=import_source_id,
                                reconciliation_type=reconciliation_type, bank_account_id=bank_account_id)
    row = BatchDefinition(
        client_id=client_id, code=code, name=name, description=description, batch_type=batch_type,
        reconciliation_type=reconciliation_type, bank_account_id=bank_account_id,
        trigger_type=trigger_type, trigger_detail=trigger_detail, import_source_id=import_source_id,
        source_ids=list(source_ids), enabled=enabled, cutoff_time=cutoff_time, sla_minutes=sla_minutes,
        owner_team=owner_team, updated_by=actor,
    )
    db.add(row)
    db.flush()
    record_event(db, entity_type="BATCH_DEFINITION", entity_id=row.id, event_type="BATCH_DEFINITION_CREATED",
                 payload={"client_id": client_id, "code": code}, actor=actor)
    return row


def update_definition(db: Session, definition_id: str, patch: dict[str, Any],
                      *, actor: str = "system") -> BatchDefinition:
    row = get_definition(db, definition_id)
    unknown = sorted(set(patch) - _EDITABLE_DEFINITION_FIELDS)
    if unknown:
        raise DomainError(f"cannot edit field(s) {unknown} on a batch definition; "
                          f"editable: {sorted(_EDITABLE_DEFINITION_FIELDS)}")

    before = {f: getattr(row, f) for f in patch}
    _validate_definition_fields(
        db, row.client_id,
        batch_type=patch.get("batch_type", row.batch_type),
        trigger_type=patch.get("trigger_type", row.trigger_type),
        source_ids=patch.get("source_ids", row.source_ids),
        import_source_id=patch.get("import_source_id", row.import_source_id),
        reconciliation_type=patch.get("reconciliation_type", row.reconciliation_type),
        bank_account_id=patch.get("bank_account_id", row.bank_account_id),
    )
    for field, value in patch.items():
        setattr(row, field, value)
    row.updated_by = actor
    db.flush()
    record_event(db, entity_type="BATCH_DEFINITION", entity_id=row.id, event_type="BATCH_DEFINITION_UPDATED",
                 payload={"before": _jsonable(before), "after": _jsonable({f: getattr(row, f) for f in patch})},
                 actor=actor)
    return row


def _jsonable(values: dict) -> dict:
    return {k: (list(v) if isinstance(v, list) else v) for k, v in values.items()}


def _validate_definition_fields(db: Session, client_id: str, *, batch_type: str, trigger_type: str,
                                source_ids: list[str] | None, import_source_id: str | None,
                                reconciliation_type: str = "BANK_GL",
                                bank_account_id: str | None = None) -> None:
    if batch_type not in BATCH_TYPES:
        raise DomainError(f"unknown batch_type {batch_type!r}; expected one of {list(BATCH_TYPES)}")
    if trigger_type not in TRIGGER_TYPES:
        raise DomainError(f"unknown trigger_type {trigger_type!r}; expected one of {list(TRIGGER_TYPES)}")
    if reconciliation_type not in recon_types.CODES:
        raise DomainError(f"unknown reconciliation_type {reconciliation_type!r}; "
                          f"expected one of {list(recon_types.CODES)}")

    rtype = recon_types.BY_CODE[reconciliation_type]
    if bank_account_id is not None:
        account = db.get(BankAccount, bank_account_id)
        if account is None:
            raise NotFoundError("BankAccount", bank_account_id)
        if account.client_id != client_id:
            raise DomainError("a bank account belonging to another client cannot be attached to this batch")
    elif rtype.scoped_to_account:
        raise DomainError(
            f"reconciliation type {rtype.label!r} reconciles one bank account and must name one. "
            "Pooling accounts nets unrelated movements together and makes every break unexplainable."
        )

    if not source_ids:
        raise DomainError("a batch definition must list at least one data source")
    known = {
        ds.source_id
        for ds in db.execute(select(DataSource).where(DataSource.client_id == client_id)).scalars()
    }
    unknown_sources = sorted(set(source_ids) - known)
    if unknown_sources:
        raise DomainError(f"data source(s) {unknown_sources} are not configured for this client "
                          f"(configured: {sorted(known)})")

    if import_source_id is not None:
        import_source = db.get(ImportSource, import_source_id)
        if import_source is None:
            raise NotFoundError("ImportSource", import_source_id)
        if import_source.client_id != client_id:
            raise DomainError("an import source belonging to another client cannot be attached to this batch")


# ---------------------------------------------------------------------------
# Derived state for the blotter
# ---------------------------------------------------------------------------

def latest_batch(db: Session, definition_id: str) -> Batch | None:
    return db.execute(
        select(Batch).where(Batch.batch_definition_id == definition_id).order_by(Batch.created_at.desc())
    ).scalars().first()


def definition_state(db: Session, definition: BatchDefinition, *, check_data: bool = True) -> dict:
    """State + data availability for one configured batch, computed fresh."""
    batch = latest_batch(db, definition.id)
    data_available: bool | None = None
    available_sources: list[str] = []
    location = None

    if definition.import_source_id:
        import_source = db.get(ImportSource, definition.import_source_id)
        if import_source is not None:
            client = db.get(Client, definition.client_id)
            location = import_sources_domain.describe_location(import_source, client.code)
            if check_data:
                found = import_sources_domain.discover(
                    import_source, client_code=client.code, wanted_source_ids=list(definition.source_ids)
                )
                available_sources = sorted(found.source_ids)
                data_available = set(definition.source_ids).issubset(found.source_ids)

    if not definition.enabled:
        state = STATE_DISABLED
    elif batch is not None and batch.status in _RUNNING_STATUSES:
        state = STATE_RUNNING
    elif batch is not None and batch.status == state_machine.FAILED:
        state = STATE_FAILED
    elif data_available is False:
        state = STATE_AWAITING_DATA
    elif batch is not None and batch.status == state_machine.CLOSED:
        state = STATE_COMPLETED
    elif data_available:
        state = STATE_DATA_AVAILABLE
    else:
        state = STATE_AWAITING_DATA

    return {
        "state": state,
        "data_available": data_available,
        "available_source_ids": available_sources,
        "missing_source_ids": sorted(set(definition.source_ids) - set(available_sources)) if check_data else [],
        "import_location": location,
        "latest_batch": batch,
    }


def next_business_date(db: Session, definition: BatchDefinition) -> str:
    """"Today" for a new run, in the CLIENT's business calendar -- not the
    server's. A server clocked in UTC is on the previous date for the whole
    first 5.5 hours of an IST business day (00:00-05:29 IST is still
    18:30-23:59 UTC the day before); using the server's own local date here
    would silently misdate batches created in that window."""
    client = db.get(Client, definition.client_id)
    tz_name = client.display_timezone if client else "Asia/Kolkata"
    return to_display_timezone(default_clock.now(), tz_name).date().isoformat()


def next_batch_code(db: Session, definition: BatchDefinition, business_date: str) -> str:
    """Human-readable and unique per re-run: MRDN_BANK_EOD/2026-09-02 for the
    first run of the day, then .../2026-09-02#2 for a re-run."""
    base = f"{definition.code}/{business_date}"
    existing = list(db.execute(
        select(Batch.batch_code).where(
            Batch.batch_definition_id == definition.id, Batch.business_date == business_date
        )
    ).scalars())
    if not existing:
        return base
    return f"{base}#{len(existing) + 1}"
