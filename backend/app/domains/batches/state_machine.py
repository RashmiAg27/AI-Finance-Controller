"""The batch lifecycle. Declared in full now (including states no milestone
before M6/M7/M8 will ever reach) so later milestones never need a migration
or an enum change here -- they only add service code that calls transition()
into a state that already exists.

Every status change in the system MUST go through transition() so the
allowed-transition guard and the audit trail are enforced in exactly one
place (spec principle: prefer explicitness over magic, prefer auditability
over convenience).
"""
from sqlalchemy.orm import Session

from app.core.audit import record_event
from app.core.clock import default_clock
from app.core.errors import InvalidTransitionError
from app.models.batch import Batch

CREATED = "CREATED"
FILES_RECEIVED = "FILES_RECEIVED"
VALIDATED = "VALIDATED"
NORMALIZED = "NORMALIZED"
RECONCILIATION_RUNNING = "RECONCILIATION_RUNNING"
RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"
EXCEPTIONS_IDENTIFIED = "EXCEPTIONS_IDENTIFIED"
EXCEPTIONS_RESOLVED = "EXCEPTIONS_RESOLVED"
TAX_PROCESSING = "TAX_PROCESSING"
SETTLEMENT_PROCESSING = "SETTLEMENT_PROCESSING"
REPORTING = "REPORTING"
CLOSED = "CLOSED"
FAILED = "FAILED"

TERMINAL_STATES = {CLOSED, FAILED}

# Forward path. FAILED is reachable from every non-terminal state and is
# handled separately below rather than repeated in every set.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    CREATED: {FILES_RECEIVED},
    FILES_RECEIVED: {VALIDATED},
    VALIDATED: {NORMALIZED},
    NORMALIZED: {RECONCILIATION_RUNNING},
    RECONCILIATION_RUNNING: {RECONCILIATION_COMPLETED},
    RECONCILIATION_COMPLETED: {EXCEPTIONS_IDENTIFIED},
    EXCEPTIONS_IDENTIFIED: {EXCEPTIONS_RESOLVED, TAX_PROCESSING},
    EXCEPTIONS_RESOLVED: {TAX_PROCESSING},
    TAX_PROCESSING: {SETTLEMENT_PROCESSING},
    SETTLEMENT_PROCESSING: {REPORTING},
    REPORTING: {CLOSED},
    CLOSED: set(),
    FAILED: set(),
}

_TIMESTAMP_FIELD = {
    FILES_RECEIVED: "files_received_at",
    VALIDATED: "validated_at",
    NORMALIZED: "normalized_at",
    RECONCILIATION_RUNNING: "reconciliation_started_at",
    RECONCILIATION_COMPLETED: "reconciliation_completed_at",
    EXCEPTIONS_IDENTIFIED: "exceptions_identified_at",
    EXCEPTIONS_RESOLVED: "exceptions_resolved_at",
    TAX_PROCESSING: "tax_processing_at",
    SETTLEMENT_PROCESSING: "settlement_processing_at",
    REPORTING: "reporting_at",
    CLOSED: "closed_at",
}


def transition(db: Session, batch: Batch, to_status: str, *, actor: str = "system",
                failure_reason: str | None = None) -> Batch:
    from_status = batch.status
    is_valid = to_status in ALLOWED_TRANSITIONS.get(from_status, set())
    is_valid_failure = to_status == FAILED and from_status not in TERMINAL_STATES
    if not (is_valid or is_valid_failure):
        raise InvalidTransitionError("Batch", from_status, to_status)

    batch.status = to_status
    now = default_clock.now()
    field = _TIMESTAMP_FIELD.get(to_status)
    if field:
        setattr(batch, field, now)
    if to_status == FAILED:
        batch.failure_reason = failure_reason

    db.flush()
    record_event(db, entity_type="BATCH", entity_id=batch.id, event_type="STATE_TRANSITION",
                 payload={"from": from_status, "to": to_status, "failure_reason": failure_reason}, actor=actor)
    return batch
