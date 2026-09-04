"""Pass 5: for transactions that Passes 1-4 could not link (no shared
reference, and no plain amount+date+counterparty match because the amounts
genuinely differ by a documented fee+tax deduction), check whether a
configured fee/tax rule fully explains the gap before anything is allowed to
fall through to ML/exception handling.

This is new candidate generation over what's still unmatched -- it is
distinct from M6's settlement decomposition, which explains an amount
difference on a pair *already* linked by reference/aggregation. If a pair
gets here, it means no reference tied them together at all; the fee/tax math
is the only thing connecting them.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.reconciliation.blocking import AmountSortedPool
from app.domains.reconciliation.evidence import EvidenceItem, MatchCandidate
from app.domains.reconciliation.txn_view import TxnView
from app.domains.tax.service import calculate_fee_and_tax
from app.schemas.config import ClientConfigSchema

RULE_ID = "PASS5_FEE_TAX_EXPLAINED"
RULE_VERSION = 1


def run(db: Session, internal_pool: list[TxnView], external_pool: list[TxnView],
        config: ClientConfigSchema) -> list[MatchCandidate]:
    rules = config.tax_fee_rules
    if rules is None:
        return []

    relevant_internal = [t for t in internal_pool if t.instrument_type == rules.applicable_when.internal_instrument_type]
    relevant_external = [t for t in external_pool if t.instrument_type == rules.applicable_when.external_instrument_type]
    if not relevant_internal or not relevant_external:
        return []

    pool = AmountSortedPool(relevant_external)
    tolerance = Decimal(str(rules.rounding_tolerance))
    candidates: list[MatchCandidate] = []
    used_external: set[str] = set()

    for internal_txn in relevant_internal:
        calc = calculate_fee_and_tax(db, internal_txn.amount, rules, instrument_type=internal_txn.instrument_type)
        net_matches = [c for c in pool.within(calc.net_amount, tolerance) if c.id not in used_external]
        if not net_matches:
            continue

        internal_date = internal_txn.date_for(rules.date_field) or internal_txn.transaction_date
        best, best_delta = None, None
        for candidate in net_matches:
            candidate_date = candidate.date_for(rules.date_field) or candidate.transaction_date
            if internal_date is None or candidate_date is None:
                continue
            delta = abs((candidate_date - internal_date).days)
            if delta <= rules.date_tolerance_days and (best is None or delta < best_delta):
                best, best_delta = candidate, delta
        if best is None:
            continue

        evidence = [
            EvidenceItem(
                evidence_type="AMOUNT_COMPARISON", field_name="amount",
                source_value=str(internal_txn.amount), target_value=str(best.amount),
                comparator="fee_tax_adjusted", passed=True,
                detail={
                    "gross_amount": str(calc.gross_amount), "fee_amount": str(calc.fee_amount),
                    "fee_rate_percent": str(calc.fee_rate_percent), "tax_amount": str(calc.tax_amount),
                    "tax_rate_percent": str(calc.tax_rate_percent), "expected_net": str(calc.net_amount),
                    "observed_net": str(best.amount), "rounding_tolerance": rules.rounding_tolerance,
                    "charges": [line.to_dict() for line in calc.charge_lines],
                    "total_deductions": str(calc.total_deductions),
                },
            ),
            EvidenceItem(
                evidence_type="TAX_RULE_APPLIED", field_name="tax_on_fee",
                source_value=calc.tax_rule.rule_id, target_value=f"{calc.tax_rule.rate_percent}%",
                comparator="tax_rule_lookup", passed=True,
                detail={
                    "rule_version": calc.tax_rule.rule_version,
                    "source_authority": calc.tax_rule.source_authority,
                    "source_reference": calc.tax_rule.source_reference,
                    "source_url": calc.tax_rule.source_url,
                    "verification_status": calc.tax_rule.verification_status,
                },
            ),
            EvidenceItem(
                evidence_type="DATE_COMPARISON", field_name=rules.date_field,
                source_value=str(internal_date),
                target_value=str(best.date_for(rules.date_field) or best.transaction_date),
                comparator="date_tolerance_days", passed=True,
                detail={"tolerance_days": rules.date_tolerance_days, "actual_delta_days": best_delta},
            ),
        ]
        candidates.append(MatchCandidate(
            source_ids=[internal_txn.id], target_ids=[best.id],
            rule_id=RULE_ID, rule_version=RULE_VERSION, match_type="EXPLAINED_BY_FEE_TAX",
            confidence=rules.confidence, evidence=evidence,
        ))
        used_external.add(best.id)

    return candidates
