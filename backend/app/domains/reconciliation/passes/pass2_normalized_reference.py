import re

from app.domains.reconciliation.blocking import suffix_index
from app.domains.reconciliation.evidence import EvidenceItem, MatchCandidate
from app.domains.reconciliation.passes.base import find_linkage_rule, resolve_condition_sides
from app.domains.reconciliation.txn_view import TxnView
from app.schemas.config import ClientConfigSchema, MatchingRule


def _digits_no_leading_zeros(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits.lstrip("0") or digits  # keep a lone "0" rather than collapsing to ""


def _partial_match(a: str, b: str) -> bool:
    """'Normalized/partial' reference equality, tolerant of the two most
    common real-world reference-number discrepancies: substring padding
    (one side wraps/truncates the other) and leading-zero differences in the
    numeric portion (e.g. a cheque number padded to a fixed width on one
    side but not the other)."""
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return _digits_no_leading_zeros(a) == _digits_no_leading_zeros(b)


def run(internal_pool: list[TxnView], external_pool: list[TxnView], rule: MatchingRule,
        config: ClientConfigSchema) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = []
    used_internal: set[str] = set()
    used_external: set[str] = set()

    for condition in rule.match_on:
        if condition.comparison != "normalized_partial":
            continue
        linkage = find_linkage_rule(config, condition.left_identifier, condition.right_identifier)
        if linkage is None:
            continue  # no client-authored statement connecting these identifier types at all

        sides = resolve_condition_sides(internal_pool, external_pool, condition.left_identifier, condition.right_identifier)
        if sides is None:
            continue
        internal_identifier_type, external_identifier_type = sides

        bucket_index = suffix_index(external_pool, external_identifier_type)
        for internal_txn in internal_pool:
            if internal_txn.id in used_internal:
                continue
            value = internal_txn.identifiers.get(internal_identifier_type)
            if not value:
                continue
            bucket = bucket_index.get(value[-6:], [])
            for external_txn in bucket:
                if external_txn.id in used_external:
                    continue
                target_value = external_txn.identifiers.get(external_identifier_type)
                if not _partial_match(value, target_value or ""):
                    continue
                evidence = [EvidenceItem(
                    evidence_type="IDENTIFIER_COMPARISON",
                    field_name=f"{internal_identifier_type}<->{external_identifier_type}",
                    source_value=value,
                    target_value=target_value,
                    comparator="normalized_partial",
                    passed=True,
                    detail={"linkage_rule_id": linkage.rule_id, "linkage_type": linkage.linkage_type},
                )]
                candidates.append(MatchCandidate(
                    source_ids=[internal_txn.id], target_ids=[external_txn.id],
                    rule_id=rule.rule_id, rule_version=rule.version, match_type="NORMALIZED_REFERENCE",
                    confidence=rule.confidence, evidence=evidence,
                ))
                used_internal.add(internal_txn.id)
                used_external.add(external_txn.id)
                break

    return candidates
