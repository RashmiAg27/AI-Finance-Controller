from app.domains.normalization.field_mapper import MappedRecord
from app.schemas.config import ClassificationRule


def _rule_matches(rule: ClassificationRule, source_id: str, haystack: str) -> bool:
    """A rule's `when` clause may combine a source_id scope with a text
    condition; every key present must match (AND) -- this is what lets a
    client's config classify the same keyword differently depending on which
    data source produced the row (e.g. a gateway's own settlement records vs
    its merchant's internal ledger, which may use similar wording)."""
    if not rule.when:
        return False
    if "source_id" in rule.when and rule.when["source_id"] != source_id:
        return False
    needle = rule.when.get("any_field_contains")
    if needle is not None and needle.upper() not in haystack:
        return False
    return True


_DEFAULTS = {"instrument_type": "OTHER", "transaction_type": "PAYMENT"}


def classify(record: MappedRecord, rules: list[ClassificationRule], source_id: str) -> dict[str, str]:
    """Returns everything the winning rule sets, not just the instrument type.

    A classification rule may now also assert `payment_method` (how the money
    moved) and `counterparty_type` (who was on the other side). The second of
    those is load-bearing: marking a sweep INTERNAL_ACCOUNT is what stops the
    cash position from counting a transfer between the client's own accounts
    as money leaving the business.

    First matching non-default rule wins; falls back to the rule marked
    `default: true`, or to OTHER/PAYMENT if the config declares no default.
    A value the record itself already carries (because a source column mapped
    straight onto it) is never overwritten by a rule -- stated data beats
    inferred data.
    """
    default_rule: ClassificationRule | None = None
    haystack = record.raw_row_text.upper()
    winner: dict[str, str] | None = None

    for rule in rules:
        if rule.default:
            default_rule = rule
            continue
        if _rule_matches(rule, source_id, haystack):
            winner = dict(rule.set)
            break

    if winner is None:
        winner = dict(default_rule.set) if default_rule else {}

    resolved = {**_DEFAULTS, **winner}
    for stated in ("payment_method", "counterparty_type"):
        value = getattr(record, stated, None)
        if value:
            resolved[stated] = value
    return resolved
