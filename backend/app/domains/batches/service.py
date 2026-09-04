from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConfigValidationError, DomainError, NotFoundError
from app.domains.batches import state_machine
from app.domains.exceptions.service import identify_exceptions
from app.domains.ingestion import service as ingestion_service
from app.domains.normalization import service as normalization_service
from app.domains.cash.service import compute_cash_position
from app.domains.forecasting.service import build_forecast
from app.domains.reconciliation.service import run_reconciliation
from app.domains.settlement.service import build_settlements_for_batch
from app.models.batch import Batch, BatchFile
from app.models.batch_definition import BatchDefinition
from app.models.client import Client
from app.models.config_version import ClientConfiguration
from app.models.data_source import DataSource
from app.models.source_file import SourceFile, SourceRecord
from app.schemas.config import ClientConfigSchema

# Signature of the optional progress hook process_batch() calls between
# stages: (stage, percent_complete, message, detail). The background runner
# uses it to write the operator log and commit intermediate progress so a
# polling UI sees the run advance; tests and the seed script pass nothing and
# get the original synchronous behaviour unchanged.
ProgressHook = Callable[[str, int, str, dict], None]


def _noop_progress(stage: str, pct: int, message: str, detail: dict) -> None:
    return None


def create_batch(db: Session, *, client_id: str, batch_code: str, actor: str = "system",
                 batch_definition_id: str | None = None, business_date: str | None = None,
                 triggered_by_type: str = "MANUAL") -> Batch:
    client = db.get(Client, client_id)
    if client is None:
        raise NotFoundError("Client", client_id)

    active_config = db.execute(
        select(ClientConfiguration).where(
            ClientConfiguration.client_id == client_id,
            ClientConfiguration.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if active_config is None:
        raise ConfigValidationError(
            f"client {client.code!r} has no ACTIVE configuration version; activate one before creating a batch"
        )

    batch = Batch(
        client_id=client_id, batch_code=batch_code, config_version_id=active_config.id, created_by=actor,
        batch_definition_id=batch_definition_id, business_date=business_date,
        triggered_by_type=triggered_by_type, triggered_by=actor, current_stage="QUEUED", progress_pct=0,
    )
    db.add(batch)
    db.flush()
    return batch


def get_batch(db: Session, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise NotFoundError("Batch", batch_id)
    return batch


def list_batches(db: Session, *, client_id: str | None = None, status: str | None = None,
                 batch_definition_id: str | None = None) -> list[Batch]:
    stmt = select(Batch)
    if client_id:
        stmt = stmt.where(Batch.client_id == client_id)
    if status:
        stmt = stmt.where(Batch.status == status)
    if batch_definition_id:
        stmt = stmt.where(Batch.batch_definition_id == batch_definition_id)
    stmt = stmt.order_by(Batch.created_at)
    return list(db.execute(stmt).scalars())


def _bound_config(db: Session, batch: Batch) -> ClientConfigSchema:
    config_row = db.get(ClientConfiguration, batch.config_version_id)
    return ClientConfigSchema.model_validate(config_row.parsed_json)


def upload_file(db: Session, *, batch: Batch, source_id: str, filename: str, content: bytes) -> SourceFile:
    if batch.status != state_machine.CREATED:
        raise DomainError(f"batch {batch.id} is {batch.status}, files can only be uploaded while CREATED")
    client = db.get(Client, batch.client_id)
    data_source = ingestion_service.get_data_source_by_code(db, client_id=batch.client_id, source_id=source_id)
    return ingestion_service.store_uploaded_file(
        db, batch=batch, client=client, data_source=data_source, filename=filename, content=content
    )


def _expected_source_ids(db: Session, batch: Batch, config: ClientConfigSchema) -> list[str]:
    """Which data sources this batch must have before it can be processed.

    A batch definition's own source list wins when there is one: a client's
    configured sources serve several different reconciliation cycles, so
    "required" is a property of the cycle, not of the source.
    """
    if batch.batch_definition_id:
        definition = db.get(BatchDefinition, batch.batch_definition_id)
        if definition is not None and definition.source_ids:
            return list(definition.source_ids)
    return [ds.source_id for ds in config.data_sources if ds.is_required]


def mark_files_complete(db: Session, batch: Batch, *, actor: str = "system") -> Batch:
    config = _bound_config(db, batch)
    uploaded_codes = set(
        db.execute(
            select(DataSource.source_id)
            .join(BatchFile, BatchFile.data_source_id == DataSource.id)
            .where(BatchFile.batch_id == batch.id)
        ).scalars()
    )

    missing = [sid for sid in _expected_source_ids(db, batch, config) if sid not in uploaded_codes]
    if missing:
        raise DomainError(f"batch {batch.id} is missing required data sources: {missing}")

    return state_machine.transition(db, batch, state_machine.FILES_RECEIVED, actor=actor)


def process_batch(db: Session, batch: Batch, *, actor: str = "system",
                  progress: ProgressHook | None = None) -> Batch:
    """Runs the batch through its full deterministic lifecycle: ingest raw
    files into SourceRecords, normalize+classify into canonical Transactions,
    run the deterministic matching engine, classify whatever remains
    unmatched into the exception queue, build the formal settlement
    decomposition for every aggregated/fee-explained match, compute the
    client's cash position and a short-term forecast from it, then close.
    Any failure moves the batch to FAILED with a recorded reason rather than
    leaving it stuck mid-pipeline."""
    if batch.status != state_machine.FILES_RECEIVED:
        raise DomainError(f"batch {batch.id} is {batch.status}, expected FILES_RECEIVED before processing")

    emit = progress or _noop_progress

    try:
        batch_files = list(db.execute(select(BatchFile).where(BatchFile.batch_id == batch.id)).scalars())
        config = _bound_config(db, batch)
        ds_config_by_source_id = {ds.source_id: ds for ds in config.data_sources}

        emit("VALIDATE", 25, f"Parsing {len(batch_files)} source file(s) against the bound configuration.", {})
        parsed_counts: dict[str, int] = {}
        for bf in batch_files:
            source_file = db.get(SourceFile, bf.source_file_id)
            data_source = db.get(DataSource, bf.data_source_id)
            ds_config = ds_config_by_source_id[data_source.source_id]
            records = ingestion_service.parse_source_file(db, source_file=source_file, sheet_name=ds_config.sheet_name)
            errors = [r for r in records if r.parse_status == "ERROR"]
            if errors:
                raise DomainError(f"{source_file.original_filename}: {errors[0].parse_error}")
            parsed_counts[data_source.source_id] = len(records)
            emit("VALIDATE", 25,
                 f"{data_source.source_id}: parsed {len(records)} row(s) from "
                 f"{source_file.original_filename} ({data_source.file_format}).",
                 {"source_id": data_source.source_id, "rows": len(records),
                  "checksum_sha256": source_file.checksum_sha256})

        state_machine.transition(db, batch, state_machine.VALIDATED, actor=actor)

        normalization_service.normalize_batch(db, batch)
        txn_count = len(db.execute(
            select(SourceRecord).where(SourceRecord.batch_id == batch.id)
        ).scalars().all())
        emit("NORMALIZE", 40,
             f"Normalized and classified {txn_count} source record(s) into canonical transactions.",
             {"source_records": txn_count, "parsed_by_source": parsed_counts})
        state_machine.transition(db, batch, state_machine.NORMALIZED, actor=actor)

        emit("MATCH", 55, "Running the deterministic matching engine (passes 1-6).", {})
        _run, engine_result = run_reconciliation(db, batch, actor=actor)
        emit("MATCH", 70, "Matching engine completed.", dict(_run.stats_json or {}))

        identify_exceptions(db, batch, engine_result)
        state_machine.transition(db, batch, state_machine.EXCEPTIONS_IDENTIFIED, actor=actor)
        emit("EXCEPTIONS", 78, "Exception classification complete.", {})

        state_machine.transition(db, batch, state_machine.TAX_PROCESSING, actor=actor)
        emit("TAX", 84, "Tax, fee and commission treatment applied to fee-explained matches.", {})

        state_machine.transition(db, batch, state_machine.SETTLEMENT_PROCESSING, actor=actor)
        settlements = build_settlements_for_batch(db, batch)
        emit("SETTLEMENT", 90, f"Built {len(settlements)} settlement decomposition(s).", {})

        state_machine.transition(db, batch, state_machine.REPORTING, actor=actor)
        cash_position = compute_cash_position(db, batch.client_id, batch)
        forecast = build_forecast(db, cash_position)
        emit("CASH", 96, "Cash position and short-term forecast recomputed for the client.",
             {"confirmed_cash": str(cash_position.confirmed_cash),
              "unreconciled_amount": str(cash_position.unreconciled_amount),
              "forecast_horizon_days": getattr(forecast, "horizon_days", None)})

        state_machine.transition(db, batch, state_machine.CLOSED, actor=actor)
        return batch

    except DomainError as exc:
        state_machine.transition(db, batch, state_machine.FAILED, actor=actor, failure_reason=str(exc))
        raise
