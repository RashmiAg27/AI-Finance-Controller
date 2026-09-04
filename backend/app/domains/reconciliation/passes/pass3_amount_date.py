from app.domains.reconciliation.blocking import AmountSortedPool
from app.domains.reconciliation.evidence import EvidenceItem, MatchCandidate
from app.domains.reconciliation.tolerance import tolerance_amount
from app.domains.reconciliation.txn_view import TxnView
from app.schemas.config import ClientConfigSchema, MatchingRule


def run(internal_pool: list[TxnView], external_pool: list[TxnView], rule: MatchingRule,
        config: ClientConfigSchema) -> list[MatchCandidate]:
    if rule.conditions is None:
        return []
    conditions = rule.conditions
    date_field = conditions.date_field
    date_tolerance_days = conditions.date_tolerance_days

    pool = AmountSortedPool(external_pool)
    candidates: list[MatchCandidate] = []
    used_external: set[str] = set()

    for internal_txn in internal_pool:
        tol = tolerance_amount(internal_txn.amount, conditions.amount_tolerance)
        amount_matches = [c for c in pool.within(internal_txn.amount, tol) if c.id not in used_external]
        if not amount_matches:
            continue

        internal_date = internal_txn.date_for(date_field) or internal_txn.transaction_date
        best = None
        best_delta = None
        for candidate in amount_matches:
            candidate_date = candidate.date_for(date_field) or candidate.transaction_date
            if internal_date is None or candidate_date is None:
                continue
            delta = abs((candidate_date - internal_date).days)
            if delta <= date_tolerance_days and (best is None or delta < best_delta):
                best, best_delta = candidate, delta

        if best is None:
            continue

        evidence = [
            EvidenceItem(
                evidence_type="AMOUNT_COMPARISON", field_name="amount",
                source_value=str(internal_txn.amount), target_value=str(best.amount),
                comparator="absolute_tolerance", passed=True,
                detail={"tolerance": str(tol), "diff": str(abs(internal_txn.amount - best.amount))},
            ),
            EvidenceItem(
                evidence_type="DATE_COMPARISON", field_name=date_field,
                source_value=str(internal_date), target_value=str(best.date_for(date_field) or best.transaction_date),
                comparator="date_tolerance_days", passed=True,
                detail={"tolerance_days": date_tolerance_days, "actual_delta_days": best_delta},
            ),
        ]
        candidates.append(MatchCandidate(
            source_ids=[internal_txn.id], target_ids=[best.id],
            rule_id=rule.rule_id, rule_version=rule.version, match_type="AMOUNT_DATE",
            confidence=rule.confidence, evidence=evidence,
        ))
        used_external.add(best.id)

    return candidates
