"""Pass 6: 1:N / N:1 (and, in principle, N:N) settlement aggregation.

Rather than a special-cased "try to sum some transactions" heuristic, this
groups whatever is still unmatched on each side by a single client-declared
aggregation identifier (e.g. a settlement-batch reference) and compares the
groups' amount sums. The relationship is represented structurally --
MatchCandidate.source_ids/target_ids simply hold more than one id on
whichever side aggregates -- using the exact same reconciliation_matches /
reconciliation_match_transactions schema Passes 1-5 already write to.
"""
from app.domains.reconciliation.blocking import identifier_index
from app.domains.reconciliation.evidence import EvidenceItem, MatchCandidate
from app.domains.reconciliation.tolerance import tolerance_amount
from app.domains.reconciliation.txn_view import TxnView
from app.schemas.config import ClientConfigSchema


def run(internal_pool: list[TxnView], external_pool: list[TxnView], config: ClientConfigSchema) -> list[MatchCandidate]:
    rules = config.aggregation_rules
    if rules is None:
        return []

    internal_groups = identifier_index(internal_pool, rules.identifier_type)
    external_groups = identifier_index(external_pool, rules.identifier_type)

    candidates: list[MatchCandidate] = []
    for key, internal_group in internal_groups.items():
        external_group = external_groups.get(key)
        if not external_group:
            continue

        # A lone 1:1 pairing on this identifier is still legitimate here --
        # aggregation_rules.identifier_type is validated to be excluded from
        # matching_rules, so nothing else could have resolved it -- it's just
        # resolved via the same amount-sum check as a true N-way group.
        internal_sum = sum((t.amount for t in internal_group), start=type(internal_group[0].amount)(0))
        external_sum = sum((t.amount for t in external_group), start=type(external_group[0].amount)(0))
        tol = tolerance_amount(internal_sum, rules.amount_tolerance)
        if abs(internal_sum - external_sum) > tol:
            continue

        internal_dates = [t.date_for(rules.date_field) or t.transaction_date for t in internal_group]
        external_dates = [t.date_for(rules.date_field) or t.transaction_date for t in external_group]
        internal_dates = [d for d in internal_dates if d is not None]
        external_dates = [d for d in external_dates if d is not None]
        if not internal_dates or not external_dates:
            continue
        span_delta = min(
            abs((ed - idt).days) for idt in internal_dates for ed in external_dates
        )
        if span_delta > rules.date_tolerance_days:
            continue

        if len(internal_group) == 1:
            cardinality_note = "ONE_TO_MANY"
        elif len(external_group) == 1:
            cardinality_note = "MANY_TO_ONE"
        else:
            cardinality_note = "MANY_TO_MANY"

        evidence = [
            EvidenceItem(
                evidence_type="AGGREGATION_KEY", field_name=rules.identifier_type,
                source_value=key, target_value=key, comparator="exact", passed=True,
                detail={"internal_group_size": len(internal_group), "external_group_size": len(external_group)},
            ),
            EvidenceItem(
                evidence_type="AMOUNT_COMPARISON", field_name="amount_sum",
                source_value=str(internal_sum), target_value=str(external_sum),
                comparator="group_sum_tolerance", passed=True,
                detail={"tolerance": str(tol), "diff": str(abs(internal_sum - external_sum)),
                        "cardinality": cardinality_note},
            ),
            EvidenceItem(
                evidence_type="DATE_COMPARISON", field_name=rules.date_field,
                source_value=str(min(internal_dates)), target_value=str(min(external_dates)),
                comparator="date_tolerance_days", passed=True,
                detail={"tolerance_days": rules.date_tolerance_days, "actual_min_delta_days": span_delta},
            ),
        ]
        candidates.append(MatchCandidate(
            source_ids=[t.id for t in internal_group], target_ids=[t.id for t in external_group],
            rule_id=rules.rule_id, rule_version=1, match_type="AGGREGATED",
            confidence=rules.confidence, evidence=evidence,
        ))

    return candidates
