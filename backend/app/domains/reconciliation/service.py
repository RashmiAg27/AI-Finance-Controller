from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import default_clock
from app.domains.batches import state_machine
from app.domains.reconciliation.engine import EngineResult, run_deterministic_passes
from app.domains.reconciliation.evidence import MatchCandidate
from app.domains.tax.service import get_tax_rule
from app.models.batch import Batch
from app.models.config_version import ClientConfiguration
from app.models.reconciliation import MatchEvidence, ReconciliationMatch, ReconciliationMatchTransaction, ReconciliationRun
from app.models.tax import TaxCalculation
from app.schemas.config import ClientConfigSchema


def _next_run_number(db: Session, batch_id: str) -> int:
    current_max = db.execute(
        select(func.max(ReconciliationRun.run_number)).where(ReconciliationRun.batch_id == batch_id)
    ).scalar_one_or_none()
    return (current_max or 0) + 1


def persist_candidates(db: Session, run_id: str, candidates: list[MatchCandidate]) -> list[ReconciliationMatch]:
    matches: list[ReconciliationMatch] = []
    for candidate in candidates:
        match = ReconciliationMatch(
            reconciliation_run_id=run_id,
            match_type=candidate.match_type,
            cardinality=candidate.cardinality,
            rule_id=candidate.rule_id,
            rule_version=candidate.rule_version,
            confidence=candidate.confidence,
            status="CONFIRMED",
        )
        db.add(match)
        db.flush()

        for txn_id in candidate.source_ids:
            db.add(ReconciliationMatchTransaction(match_id=match.id, transaction_id=txn_id, side="SOURCE"))
        for txn_id in candidate.target_ids:
            db.add(ReconciliationMatchTransaction(match_id=match.id, transaction_id=txn_id, side="TARGET"))
        for ev in candidate.evidence:
            db.add(MatchEvidence(
                match_id=match.id, evidence_type=ev.evidence_type, field_name=ev.field_name,
                source_value=ev.source_value, target_value=ev.target_value, comparator=ev.comparator,
                passed=ev.passed, detail_json=ev.detail,
            ))

        if candidate.match_type == "EXPLAINED_BY_FEE_TAX":
            _persist_tax_calculation(db, match.id, candidate)

        matches.append(match)
    db.flush()
    return matches


def _persist_tax_calculation(db: Session, match_id: str, candidate: MatchCandidate) -> None:
    """Pass 5 attaches its evidence as EvidenceItems on the match; this
    re-derives a formal TaxCalculation row from that same evidence so 'why
    was this tax amount calculated?' can be answered from a dedicated,
    queryable record rather than by parsing evidence JSON."""
    amount_evidence = next(e for e in candidate.evidence if e.evidence_type == "AMOUNT_COMPARISON")
    tax_rule_evidence = next(e for e in candidate.evidence if e.evidence_type == "TAX_RULE_APPLIED")
    detail = amount_evidence.detail
    tax_rule = get_tax_rule(db, tax_rule_evidence.source_value)

    db.add(TaxCalculation(
        tax_rule_id=tax_rule.id,
        reconciliation_match_id=match_id,
        gross_amount=Decimal(detail["gross_amount"]),
        fee_amount=Decimal(detail["fee_amount"]),
        taxable_amount=Decimal(detail["fee_amount"]),  # tax is levied on the fee, not the gross principal
        tax_amount=Decimal(detail["tax_amount"]),
        net_amount=Decimal(detail["expected_net"]),
        calculation_detail=detail,
    ))


def run_reconciliation(db: Session, batch: Batch, *, actor: str = "system") -> tuple[ReconciliationRun, EngineResult]:
    state_machine.transition(db, batch, state_machine.RECONCILIATION_RUNNING, actor=actor)

    config_row = db.get(ClientConfiguration, batch.config_version_id)
    config = ClientConfigSchema.model_validate(config_row.parsed_json)

    run = ReconciliationRun(
        batch_id=batch.id,
        run_number=_next_run_number(db, batch.id),
        config_version_id=batch.config_version_id,
        status="RUNNING",
    )
    db.add(run)
    db.flush()

    result = run_deterministic_passes(db, batch, config)
    persist_candidates(db, run.id, result.all_candidates)

    run.status = "COMPLETED"
    run.completed_at = default_clock.now()
    run.stats_json = {
        "matches_by_pass": {str(p): len(c) for p, c in result.candidates_by_pass.items()},
        "total_matches": len(result.all_candidates),
        "unmatched_internal": len(result.remaining_internal),
        "unmatched_external": len(result.remaining_external),
    }
    db.flush()

    state_machine.transition(db, batch, state_machine.RECONCILIATION_COMPLETED, actor=actor)
    return run, result
