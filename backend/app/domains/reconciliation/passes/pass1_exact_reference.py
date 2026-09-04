from app.domains.reconciliation.blocking import identifier_index
from app.domains.reconciliation.evidence import EvidenceItem, MatchCandidate
from app.domains.reconciliation.passes.base import find_linkage_rule, resolve_condition_sides
from app.domains.reconciliation.txn_view import TxnView
from app.schemas.config import ClientConfigSchema, MatchingRule


def run(internal_pool: list[TxnView], external_pool: list[TxnView], rule: MatchingRule,
        config: ClientConfigSchema) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = []
    used_internal: set[str] = set()
    used_external: set[str] = set()

    for condition in rule.match_on:
        if condition.comparison != "exact":
            continue
        linkage = find_linkage_rule(config, condition.left_identifier, condition.right_identifier)
        if linkage is None or linkage.linkage_type != "DIRECT_EQUIVALENT":
            # No explicit client-authored statement that these identifier
            # types are the same economic reference -- refuse to match on
            # them, regardless of what matching_rules.match_on says.
            continue

        # match_on only names two identifier types -- which one is actually
        # populated on the INTERNAL vs EXTERNAL source is a fact about the
        # client's data, not something the rule hardcodes either way.
        sides = resolve_condition_sides(internal_pool, external_pool, condition.left_identifier, condition.right_identifier)
        if sides is None:
            continue
        internal_identifier_type, external_identifier_type = sides

        index = identifier_index(external_pool, external_identifier_type)
        for internal_txn in internal_pool:
            if internal_txn.id in used_internal:
                continue
            value = internal_txn.identifiers.get(internal_identifier_type)
            if not value:
                continue
            for external_txn in index.get(value, []):
                if external_txn.id in used_external:
                    continue
                evidence = [EvidenceItem(
                    evidence_type="IDENTIFIER_COMPARISON",
                    field_name=f"{internal_identifier_type}<->{external_identifier_type}",
                    source_value=value,
                    target_value=external_txn.identifiers.get(external_identifier_type),
                    comparator="exact",
                    passed=True,
                    detail={"linkage_rule_id": linkage.rule_id, "linkage_type": linkage.linkage_type},
                )]
                candidates.append(MatchCandidate(
                    source_ids=[internal_txn.id], target_ids=[external_txn.id],
                    rule_id=rule.rule_id, rule_version=rule.version, match_type="EXACT_REFERENCE",
                    confidence=rule.confidence, evidence=evidence,
                ))
                used_internal.add(internal_txn.id)
                used_external.add(external_txn.id)
                break

    return candidates
