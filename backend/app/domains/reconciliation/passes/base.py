from app.domains.reconciliation.txn_view import TxnView
from app.schemas.config import ClientConfigSchema, IdentifierLinkageRule


def pool_identifier_types(pool: list[TxnView]) -> set[str]:
    return {itype for t in pool for itype, value in t.identifiers.items() if value}


def resolve_condition_sides(
    internal_pool: list[TxnView], external_pool: list[TxnView], left_identifier: str, right_identifier: str
) -> tuple[str, str] | None:
    """A matching_rules.match_on condition names two identifier types
    (`left_identifier`/`right_identifier`) without hardcoding which one lives
    on the INTERNAL vs EXTERNAL source -- that's a fact about the client's
    data sources, not about the rule. Returns (internal_side_type,
    external_side_type), or None if the condition can't be resolved against
    the actual pools (e.g. neither side carries one of the two types)."""
    internal_types = pool_identifier_types(internal_pool)
    external_types = pool_identifier_types(external_pool)

    if left_identifier in internal_types and right_identifier in external_types:
        return left_identifier, right_identifier
    if right_identifier in internal_types and left_identifier in external_types:
        return right_identifier, left_identifier
    return None


def find_linkage_rule(
    config: ClientConfigSchema, left_identifier: str, right_identifier: str
) -> IdentifierLinkageRule | None:
    """The one place the engine is allowed to ask 'has this client explicitly
    stated these two identifier types refer to the same economic reference?'.
    Never assume equivalence just because two fields are both configured as
    identifiers -- only an identifier_linkage entry can establish that."""
    for rule in config.identifier_linkage:
        forward = (rule.source_identifier_type, rule.target_identifier_type) == (left_identifier, right_identifier)
        backward = (rule.source_identifier_type, rule.target_identifier_type) == (right_identifier, left_identifier)
        if forward or backward:
            return rule
    return None
