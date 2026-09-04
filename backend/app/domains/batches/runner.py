"""Executes a configured batch end to end, in the background, with a live
operator log.

Runs are serialised through a single worker thread on purpose: SQLite under
WAL tolerates exactly one writer, and a reconciliation platform queueing its
overnight cycles behind one another is the honest behaviour anyway -- "Run
all" enqueues, it does not fan out. The API returns as soon as the Batch row
exists, so the UI can poll status/logs while the pipeline advances.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import DomainError
from app.db.session import SessionLocal
from app.domains.batches import run_log, service as batch_service, state_machine
from app.domains.batches.definitions import get_definition
from app.domains.ingestion import import_sources as import_sources_domain
from app.domains.ingestion import service as ingestion_service
from app.models.batch import Batch
from app.models.client import Client
from app.models.exception_ import Exception_, ExceptionTransaction
from app.models.import_source import ImportSource
from app.models.reconciliation import ReconciliationRun
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="batch-runner")
_pending: dict[str, Future] = {}
_pending_lock = threading.Lock()


def submit(batch_id: str) -> None:
    """Queues an already-created, already-committed batch for execution."""
    with _pending_lock:
        _pending[batch_id] = _executor.submit(_execute_in_new_session, batch_id)


def wait_for_all(timeout: float | None = None) -> None:
    """Blocks until every queued run has finished. For the seed script and
    tests -- the API never calls this."""
    with _pending_lock:
        futures = list(_pending.values())
    for future in futures:
        future.result(timeout=timeout)


def _execute_in_new_session(batch_id: str) -> None:
    db = SessionLocal()
    try:
        execute(db, batch_id)
    except Exception:  # noqa: BLE001 -- a worker thread must never die silently
        logger.exception("batch run %s failed unexpectedly", batch_id)
    finally:
        db.close()
        with _pending_lock:
            _pending.pop(batch_id, None)


def _pause() -> None:
    """Deliberate inter-stage pause so a run is observable in the UI. Set
    BATCH_STAGE_DELAY_SECONDS=0 to remove it entirely."""
    delay = settings.batch_stage_delay_seconds
    if delay > 0:
        time.sleep(delay)


def execute(db: Session, batch_id: str) -> Batch:
    """The full run: fetch from the configured import source, then process.
    Every outcome -- including 'the files never arrived' -- ends with the
    batch in a terminal state and a log that explains itself."""
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise DomainError(f"no batch {batch_id!r} to execute")

    client = db.get(Client, batch.client_id)
    definition = get_definition(db, batch.batch_definition_id) if batch.batch_definition_id else None

    _set_progress(db, batch, "IMPORT", 5)
    run_log.log(db, batch.id, "IMPORT",
                f"Run started for {definition.name if definition else batch.batch_code} "
                f"(business date {batch.business_date or 'n/a'}, trigger {batch.triggered_by_type}, "
                f"requested by {batch.triggered_by}).",
                detail={"batch_code": batch.batch_code,
                        "config_version_id": batch.config_version_id})
    db.commit()

    try:
        if definition is None:
            raise DomainError("this batch has no configured definition and cannot be run automatically")
        _import_files(db, batch, definition)
        _pause()

        batch_service.mark_files_complete(db, batch, actor=batch.triggered_by)
        run_log.log(db, batch.id, "IMPORT", "All required data sources are present; batch accepted for processing.")
        _set_progress(db, batch, "VALIDATE", 20)
        db.commit()

        def progress(stage: str, pct: int, message: str, detail: dict) -> None:
            run_log.log(db, batch.id, stage, message, detail=detail)
            _set_progress(db, batch, stage, pct)
            db.commit()
            _pause()

        batch_service.process_batch(db, batch, actor=batch.triggered_by, progress=progress)

        _log_exceptions(db, batch)
        _log_final_summary(db, batch)
        _set_progress(db, batch, "CLOSED", 100)
        db.commit()
        return batch

    except DomainError as exc:
        db.rollback()
        batch = db.get(Batch, batch_id)
        _fail(db, batch, stage=batch.current_stage or "IMPORT", reason=str(exc))
        db.commit()
        return batch
    except Exception as exc:  # noqa: BLE001 -- unexpected errors must still land in the log
        db.rollback()
        batch = db.get(Batch, batch_id)
        _fail(db, batch, stage=batch.current_stage or "IMPORT",
              reason=f"unexpected {type(exc).__name__}: {exc}")
        db.commit()
        return batch


def _set_progress(db: Session, batch: Batch, stage: str, pct: int) -> None:
    batch.current_stage = stage
    batch.progress_pct = pct
    db.flush()


def _fail(db: Session, batch: Batch, *, stage: str, reason: str) -> None:
    run_log.log(db, batch.id, stage, reason, level="ERROR",
                detail={"failed_stage": stage, "batch_code": batch.batch_code})
    if batch.status not in state_machine.TERMINAL_STATES:
        state_machine.transition(db, batch, state_machine.FAILED, actor=batch.triggered_by, failure_reason=reason)
    batch.current_stage = stage
    batch.progress_pct = 100
    db.flush()


def _import_files(db: Session, batch: Batch, definition) -> None:
    client = db.get(Client, batch.client_id)
    if not definition.import_source_id:
        raise DomainError(f"batch definition {definition.code!r} has no import source configured")

    import_source = db.get(ImportSource, definition.import_source_id)
    run_log.log(db, batch.id, "IMPORT",
                f"Import source: {import_source.name} [{import_source.kind}]",
                detail={"import_source_code": import_source.code, "kind": import_source.kind,
                        "connection": dict(import_source.connection_json or {})})

    outcome = import_sources_domain.discover(
        import_source, client_code=client.code, wanted_source_ids=list(definition.source_ids)
    )
    run_log.log_many(db, batch.id, "IMPORT", outcome.log_lines)

    import_source.last_polled_at = batch.created_at
    import_source.last_status = "OK" if outcome.files else "EMPTY"
    import_source.last_message = f"{len(outcome.files)} file(s) at {outcome.location}"

    # Commit the connection narration before anything that can fail. A run
    # that dies because the feed never arrived must still show *where* it
    # looked and *what it found* -- that is the whole diagnostic value, and
    # rolling the failed transaction back would otherwise discard it.
    db.commit()

    stored_source_ids: set[str] = set()
    for discovered in outcome.files:
        if discovered.source_id in stored_source_ids:
            run_log.log(db, batch.id, "IMPORT",
                        f"Ignored duplicate file '{discovered.filename}': data source "
                        f"'{discovered.source_id}' was already supplied by an earlier file.",
                        level="WARN")
            continue
        data_source = ingestion_service.get_data_source_by_code(
            db, client_id=batch.client_id, source_id=discovered.source_id
        )
        try:
            source_file = ingestion_service.store_uploaded_file(
                db, batch=batch, client=client, data_source=data_source,
                filename=discovered.filename, content=discovered.content,
            )
        except FileExistsError as exc:
            # Raw files are immutable once written, so this means a previous
            # run already claimed this path. Say what actually happened rather
            # than surfacing a bare filesystem error.
            raise DomainError(
                f"'{discovered.filename}' was already stored for batch {batch.batch_code!r} "
                f"({exc}). Raw files are never overwritten -- clear the stale run's raw storage "
                "or re-run the batch, which allocates a new batch code."
            ) from exc
        stored_source_ids.add(discovered.source_id)
        run_log.log(db, batch.id, "IMPORT",
                    f"Stored '{discovered.filename}' as data source '{discovered.source_id}' "
                    f"({source_file.size_bytes:,} bytes, sha256 {source_file.checksum_sha256[:12]}...).",
                    detail={"origin": discovered.origin, "source_id": discovered.source_id,
                            "checksum_sha256": source_file.checksum_sha256})

    db.commit()

    missing = sorted(set(definition.source_ids) - stored_source_ids)
    if missing:
        raise DomainError(
            f"no data available for required source(s) {missing} at {outcome.location}. "
            f"Expected a file named '<source_id>__<date>.<ext>' for each."
        )


def _log_exceptions(db: Session, batch: Batch) -> None:
    """Every exception is written into the batch log in full -- type,
    severity, money at risk, the system's own likely cause and recommended
    action -- so the log is self-contained evidence rather than a pointer."""
    exceptions = list(db.execute(
        select(Exception_).where(Exception_.batch_id == batch.id).order_by(Exception_.severity)
    ).scalars())
    if not exceptions:
        run_log.log(db, batch.id, "EXCEPTIONS", "No exceptions raised: every transaction was resolved.")
        return

    run_log.log(db, batch.id, "EXCEPTIONS",
                f"{len(exceptions)} exception(s) raised and queued for review.",
                level="WARN", detail={"count": len(exceptions)})

    for exc in exceptions:
        txn_ids = list(db.execute(
            select(ExceptionTransaction.transaction_id).where(ExceptionTransaction.exception_id == exc.id)
        ).scalars())
        references = []
        for txn_id in txn_ids:
            txn = db.get(Transaction, txn_id)
            if txn is not None:
                references.append({
                    "transaction_id": txn.id, "source_id": txn.source_id,
                    "reference": txn.canonical_reference, "amount": str(txn.amount),
                    "counterparty": txn.counterparty, "transaction_date": str(txn.transaction_date),
                })
        run_log.log(
            db, batch.id, "EXCEPTIONS",
            f"[{exc.severity}] {exc.exception_type} -- amount at risk "
            f"{exc.amount_impact if exc.amount_impact is not None else 'n/a'}: {exc.likely_cause}",
            level="EXCEPTION",
            detail={
                "exception_id": exc.id, "exception_type": exc.exception_type, "severity": exc.severity,
                "status": exc.status, "amount_impact": str(exc.amount_impact) if exc.amount_impact else None,
                "likely_cause": exc.likely_cause, "confidence": exc.confidence,
                "recommended_action": exc.recommended_action, "transactions": references,
            },
        )


def _log_final_summary(db: Session, batch: Batch) -> None:
    run = db.execute(
        select(ReconciliationRun)
        .where(ReconciliationRun.batch_id == batch.id)
        .order_by(ReconciliationRun.run_number.desc())
    ).scalars().first()
    stats = dict(run.stats_json or {}) if run else {}
    run_log.log(db, batch.id, "COMPLETE",
                f"Batch {batch.batch_code} closed successfully.",
                detail={"stats": stats, "reconciliation_run_id": run.id if run else None})
