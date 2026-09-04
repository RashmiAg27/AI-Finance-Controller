from dataclasses import dataclass

from app.domains.normalization import value_normalizers as vn
from app.schemas.config import ClientConfigSchema, DataSourceConfig


@dataclass
class ResolvedIdentifier:
    identifier_type: str
    value_raw: str
    value_normalized: str
    is_primary: bool
    linked_via_rule_id: str | None


def _linkage_rule_ids_touching(config: ClientConfigSchema, identifier_type: str) -> list[str]:
    return [
        rule.rule_id
        for rule in config.identifier_linkage
        if identifier_type in (rule.source_identifier_type, rule.target_identifier_type)
    ]


def resolve_identifiers(
    raw_identifiers: dict[str, str], ds_config: DataSourceConfig, config: ClientConfigSchema
) -> tuple[list[ResolvedIdentifier], str | None]:
    """Normalize every identifier extracted for this record and pick the
    canonical_reference via identifier_priority. Returns (identifiers, canonical_reference).

    linked_via_rule_id is populated purely as descriptive metadata (which
    identifier_linkage rule, if any, could connect this identifier to the
    other side) -- Pass 1/2 matching (M2) still re-checks the rule itself
    before treating two transactions as equivalent; this field only saves it
    from re-deriving "does a rule exist at all" per comparison.
    """
    identifier_rules = {r.identifier_type: r.operations for r in config.normalization_rules.identifier_rules}

    resolved: list[ResolvedIdentifier] = []
    for identifier_type, raw_value in raw_identifiers.items():
        ops = identifier_rules.get(identifier_type, [])
        normalized = vn.apply_string_operations(raw_value, ops) if ops else raw_value.strip()
        rule_ids = _linkage_rule_ids_touching(config, identifier_type)
        resolved.append(ResolvedIdentifier(
            identifier_type=identifier_type,
            value_raw=raw_value,
            value_normalized=normalized,
            is_primary=False,
            linked_via_rule_id=rule_ids[0] if rule_ids else None,
        ))

    canonical_reference = None
    for preferred_type in ds_config.identifier_priority:
        match = next((r for r in resolved if r.identifier_type == preferred_type and r.value_normalized), None)
        if match:
            match.is_primary = True
            canonical_reference = match.value_normalized
            break

    return resolved, canonical_reference
