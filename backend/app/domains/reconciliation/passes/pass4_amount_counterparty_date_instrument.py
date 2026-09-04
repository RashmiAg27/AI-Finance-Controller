from rapidfuzz import fuzz

from app.domains.reconciliation.blocking import AmountSortedPool
from app.domains.reconciliation.evidence import EvidenceItem, MatchCandidate
from app.domains.reconciliation.tolerance import tolerance_amount
from app.domains.reconciliation.txn_view import TxnView
from app.schemas.config import ClientConfigSchema, MatchingRule


def _counterparty_text(txn: TxnView) -> str:
    """Falls back to narration/description when a source has no clean
    counterparty column -- real bank statements routinely lack one, so a
    Pass 4 that only ever looked at `counterparty` would never fire for them.
    This mirrors how a human reconciler reads a bank narration."""
    return txn.counterparty or txn.description or ""


def run(internal_pool: list[TxnView], external_pool: list[TxnView], rule: MatchingRule,
        config: ClientConfigSchema) -> list[MatchCandidate]:
    if rule.conditions is None:
        return []
    conditions = rule.conditions
    date_field = conditions.date_field
    threshold = conditions.counterparty_similarity_threshold or 0.0

    pool = AmountSortedPool(external_pool)
    candidates: list[MatchCandidate] = []
    used_external: set[str] = set()

    for internal_txn in internal_pool:
        tol = tolerance_amount(internal_txn.amount, conditions.amount_tolerance)
        amount_matches = [c for c in pool.within(internal_txn.amount, tol) if c.id not in used_external]
        if conditions.instrument_type_match == "exact":
            amount_matches = [c for c in amount_matches if c.instrument_type == internal_txn.instrument_type]
        if not amount_matches:
            continue

        internal_date = internal_txn.date_for(date_field) or internal_txn.transaction_date
        best, best_score, best_delta = None, -1.0, None
        for candidate in amount_matches:
            candidate_date = candidate.date_for(date_field) or candidate.transaction_date
            if internal_date is None or candidate_date is None:
                continue
            delta = abs((candidate_date - internal_date).days)
            if delta > conditions.date_tolerance_days:
                continue
            similarity = fuzz.token_sort_ratio(_counterparty_text(internal_txn), _counterparty_text(candidate)) / 100.0
            if similarity < threshold:
                continue
            if similarity > best_score:
                best, best_score, best_delta = candidate, similarity, delta

        if best is None:
            continue

        evidence = [
            EvidenceItem(
                evidence_type="AMOUNT_COMPARISON", field_name="amount",
                source_value=str(internal_txn.amount), target_value=str(best.amount),
                comparator="absolute_tolerance", passed=True, detail={"tolerance": str(tol)},
            ),
            EvidenceItem(
                evidence_type="DATE_COMPARISON", field_name=date_field,
                source_value=str(internal_date), target_value=str(best.date_for(date_field) or best.transaction_date),
                comparator="date_tolerance_days", passed=True,
                detail={"tolerance_days": conditions.date_tolerance_days, "actual_delta_days": best_delta},
            ),
            EvidenceItem(
                evidence_type="COUNTERPARTY_SIMILARITY", field_name="counterparty",
                source_value=_counterparty_text(internal_txn), target_value=_counterparty_text(best),
                comparator="fuzzy_token_sort_ratio", passed=True,
                detail={"threshold": threshold, "similarity": best_score,
                        "note": "falls back to narration/description when counterparty is not a mapped field"},
            ),
            EvidenceItem(
                evidence_type="INSTRUMENT_COMPARISON", field_name="instrument_type",
                source_value=internal_txn.instrument_type, target_value=best.instrument_type,
                comparator=conditions.instrument_type_match, passed=True, detail={},
            ),
        ]
        candidates.append(MatchCandidate(
            source_ids=[internal_txn.id], target_ids=[best.id],
            rule_id=rule.rule_id, rule_version=rule.version,
            match_type="AMOUNT_COUNTERPARTY_DATE_INSTRUMENT",
            confidence=rule.confidence, evidence=evidence,
        ))
        used_external.add(best.id)

    return candidates
