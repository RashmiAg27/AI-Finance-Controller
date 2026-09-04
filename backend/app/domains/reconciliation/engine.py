"""Orchestrates the deterministic matching passes over a batch's transaction
pools. Pass numbers 1-4 are driven by config.matching_rules; 5 (tax/fee
explained discrepancy, M3), 6 (aggregation, M4), each have their own
dispatch treatment below since they're driven by a different config section
(and, for 5, need a DB session for tax rule lookups) rather than a
MatchingRule. 7 (ML, M5b) will do the same when it lands.
"""
from sqlalchemy.orm import Session

from app.domains.reconciliation.evidence import MatchCandidate
from app.domains.reconciliation.passes import (
    pass1_exact_reference,
    pass2_normalized_reference,
    pass3_amount_date,
    pass4_amount_counterparty_date_instrument,
    pass5_fee_tax_explained,
    pass6_aggregation,
)
from app.domains.reconciliation.txn_view import TxnView, load_transaction_views
from app.models.batch import Batch
from app.schemas.config import ClientConfigSchema

PASS_DISPATCH = {
    1: pass1_exact_reference.run,
    2: pass2_normalized_reference.run,
    3: pass3_amount_date.run,
    4: pass4_amount_counterparty_date_instrument.run,
}


def _shrink_pools(
    internal_pool: list[TxnView], external_pool: list[TxnView], candidates: list[MatchCandidate]
) -> tuple[list[TxnView], list[TxnView]]:
    if not candidates:
        return internal_pool, external_pool
    matched_internal_ids = {tid for c in candidates for tid in c.source_ids}
    matched_external_ids = {tid for c in candidates for tid in c.target_ids}
    return (
        [t for t in internal_pool if t.id not in matched_internal_ids],
        [t for t in external_pool if t.id not in matched_external_ids],
    )


class EngineResult:
    def __init__(self):
        self.candidates_by_pass: dict[int, list[MatchCandidate]] = {}
        self.remaining_internal: list[TxnView] = []
        self.remaining_external: list[TxnView] = []

    @property
    def all_candidates(self) -> list[MatchCandidate]:
        out: list[MatchCandidate] = []
        for candidates in self.candidates_by_pass.values():
            out.extend(candidates)
        return out


def run_deterministic_passes(db: Session, batch: Batch, config: ClientConfigSchema) -> EngineResult:
    internal_pool, external_pool = load_transaction_views(db, batch, config)
    result = EngineResult()

    rules_by_pass: dict[int, list] = {}
    for rule in config.matching_rules:
        rules_by_pass.setdefault(rule.pass_number, []).append(rule)

    for pass_number in sorted(p for p in rules_by_pass if p in PASS_DISPATCH):
        pass_fn = PASS_DISPATCH[pass_number]
        pass_candidates: list[MatchCandidate] = []
        for rule in rules_by_pass[pass_number]:
            pass_candidates.extend(pass_fn(internal_pool, external_pool, rule, config))

        internal_pool, external_pool = _shrink_pools(internal_pool, external_pool, pass_candidates)
        result.candidates_by_pass[pass_number] = pass_candidates

    pass5_candidates = pass5_fee_tax_explained.run(db, internal_pool, external_pool, config)
    internal_pool, external_pool = _shrink_pools(internal_pool, external_pool, pass5_candidates)
    result.candidates_by_pass[5] = pass5_candidates

    pass6_candidates = pass6_aggregation.run(internal_pool, external_pool, config)
    internal_pool, external_pool = _shrink_pools(internal_pool, external_pool, pass6_candidates)
    result.candidates_by_pass[6] = pass6_candidates

    result.remaining_internal = internal_pool
    result.remaining_external = external_pool
    return result
