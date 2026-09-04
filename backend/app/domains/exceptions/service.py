from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.clock import default_clock
from app.domains.exceptions.classifier import ExceptionDraft, classify_remaining
from app.domains.reconciliation.engine import EngineResult
from app.models.batch import Batch
from app.models.exception_ import Exception_, ExceptionEvidence, ExceptionTransaction

# Prototype severity heuristic based on financial materiality -- no client
# configures this yet (only ageing thresholds are config-driven so far); it
# exists so the exception queue is triageable at all, not as a claimed
# accounting standard.
_HIGH_AMOUNT_THRESHOLD = Decimal(50000)
_MEDIUM_AMOUNT_THRESHOLD = Decimal(5000)


def _severity_for(draft: ExceptionDraft) -> str:
    if draft.amount_impact is None:
        return "MEDIUM"
    if draft.amount_impact >= _HIGH_AMOUNT_THRESHOLD:
        return "HIGH"
    if draft.amount_impact >= _MEDIUM_AMOUNT_THRESHOLD:
        return "MEDIUM"
    return "LOW"


_RECOMMENDED_ACTION = {
    "DUPLICATE": "Review both postings and cancel/write off the duplicate.",
    "MISSING_EXTERNAL_RECORD": "Confirm with the bank/gateway whether this transaction settled; check for a delayed feed.",
    "MISSING_INTERNAL_RECORD": "Confirm this external movement corresponds to a business transaction; check for an unposted internal entry.",
    "AMOUNT_MISMATCH": "Investigate the amount difference against fee/tax/adjustment documentation; escalate if unexplained.",
    "TIMING_DIFFERENCE": "Likely to self-resolve if within the next processing cycle; monitor before escalating.",
    "COUNTERPARTY_MISMATCH": "Manually verify counterparty identity before confirming or rejecting the candidate match.",
    "UNEXPLAINED": "Requires manual investigation -- no plausible automated explanation was found.",
}


def identify_exceptions(db: Session, batch: Batch, engine_result: EngineResult) -> list[Exception_]:
    drafts = classify_remaining(engine_result.remaining_internal, engine_result.remaining_external)
    now = default_clock.now()

    exceptions: list[Exception_] = []
    for draft in drafts:
        exception = Exception_(
            batch_id=batch.id,
            transaction_id=draft.primary_transaction_id,
            exception_type=draft.exception_type,
            severity=_severity_for(draft),
            status="OPEN",
            amount_impact=draft.amount_impact,
            likely_cause=draft.likely_cause,
            confidence=draft.confidence,
            recommended_action=_RECOMMENDED_ACTION.get(draft.exception_type, _RECOMMENDED_ACTION["UNEXPLAINED"]),
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(exception)
        db.flush()

        db.add(ExceptionEvidence(
            exception_id=exception.id, evidence_type="CLASSIFICATION",
            field_name="exception_type", value_observed=draft.exception_type,
            comparator="heuristic_classification",
            detail_json={"confidence": draft.confidence, "related_transaction_ids": draft.related_transaction_ids},
        ))
        db.add(ExceptionTransaction(exception_id=exception.id, transaction_id=draft.primary_transaction_id, role="PRIMARY"))
        for related_id in draft.related_transaction_ids:
            db.add(ExceptionTransaction(exception_id=exception.id, transaction_id=related_id, role="RELATED"))

        exceptions.append(exception)

    db.flush()
    return exceptions
