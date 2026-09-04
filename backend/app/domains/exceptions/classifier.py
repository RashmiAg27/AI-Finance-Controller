"""Classifies whatever the deterministic engine (Passes 1-6) could not
resolve into the exception taxonomy (spec section 11), each with a plain-
language likely_cause and, where a plausible near-miss exists, the
candidate transaction that was considered and rejected -- so the evidence
trail shows *why* it wasn't matched, not just that it wasn't.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from app.domains.reconciliation.txn_view import TxnView

# A "near miss" band for AMOUNT_MISMATCH: how close two transactions' amounts
# must be, relative to the larger amount, before a genuinely-unrelated
# candidate is not offered as a plausible explanation. This is a prototype
# heuristic (no client configures it yet), not a claimed accounting rule.
_AMOUNT_MISMATCH_RELATIVE_BAND = 0.10
_TIMING_LOOSE_DATE_DAYS = 10


@dataclass
class ExceptionDraft:
    primary_transaction_id: str
    exception_type: str
    likely_cause: str
    amount_impact: Decimal | None
    confidence: float
    related_transaction_ids: list[str] = field(default_factory=list)


def _duplicates_by_canonical_reference(pool: list[TxnView]) -> tuple[list[ExceptionDraft], list[TxnView]]:
    groups: dict[str, list[TxnView]] = {}
    for t in pool:
        if t.canonical_reference:
            groups.setdefault(t.canonical_reference, []).append(t)

    drafts: list[ExceptionDraft] = []
    duplicate_ids: set[str] = set()
    for ref, group in groups.items():
        if len(group) < 2:
            continue
        for t in group:
            others = [o.id for o in group if o.id != t.id]
            drafts.append(ExceptionDraft(
                primary_transaction_id=t.id, exception_type="DUPLICATE",
                likely_cause=f"{len(group)} transactions on this side share canonical_reference {ref!r} "
                             "with no other side able to absorb more than one -- likely a duplicate posting.",
                amount_impact=t.amount, confidence=0.7, related_transaction_ids=others,
            ))
            duplicate_ids.add(t.id)

    remaining = [t for t in pool if t.id not in duplicate_ids]
    return drafts, remaining


def _nearest_by_amount(txn: TxnView, candidates: list[TxnView]) -> tuple[TxnView, Decimal] | None:
    if not candidates:
        return None
    best = min(candidates, key=lambda c: abs(c.amount - txn.amount))
    return best, abs(best.amount - txn.amount)


def _classify_unmatched(txn: TxnView, other_pool: list[TxnView], missing_type: str) -> ExceptionDraft:
    nearest = _nearest_by_amount(txn, other_pool)
    if nearest is None:
        return ExceptionDraft(
            primary_transaction_id=txn.id, exception_type=missing_type,
            likely_cause="No transaction remains on the other side to compare against in this batch.",
            amount_impact=txn.amount, confidence=0.9,
        )

    candidate, diff = nearest
    relative = diff / txn.amount if txn.amount else Decimal(1)

    if diff == 0:
        date_delta = abs((candidate.transaction_date - txn.transaction_date).days)
        if date_delta > _TIMING_LOOSE_DATE_DAYS:
            return ExceptionDraft(
                primary_transaction_id=txn.id, exception_type="TIMING_DIFFERENCE",
                likely_cause=f"Same amount ({txn.amount}) found on the other side but {date_delta} days apart, "
                             "beyond any pass's configured date tolerance.",
                amount_impact=Decimal(0), confidence=0.6, related_transaction_ids=[candidate.id],
            )
        return ExceptionDraft(
            primary_transaction_id=txn.id, exception_type="COUNTERPARTY_MISMATCH",
            likely_cause=f"Same amount ({txn.amount}) and a nearby date were found on the other side, but "
                         "counterparty/instrument details did not satisfy any pass's matching threshold.",
            amount_impact=Decimal(0), confidence=0.5, related_transaction_ids=[candidate.id],
        )

    if relative <= _AMOUNT_MISMATCH_RELATIVE_BAND:
        return ExceptionDraft(
            primary_transaction_id=txn.id, exception_type="AMOUNT_MISMATCH",
            likely_cause=f"A plausible counterpart exists on the other side but differs by {diff} "
                         f"({relative:.1%} of this transaction's amount), beyond configured tolerance and not "
                         "explained by any configured fee/tax rule.",
            amount_impact=diff, confidence=0.55, related_transaction_ids=[candidate.id],
        )

    return ExceptionDraft(
        primary_transaction_id=txn.id, exception_type=missing_type,
        likely_cause=f"The closest amount available on the other side ({candidate.amount}) differs by {diff}, "
                     "too large to be a plausible match.",
        amount_impact=txn.amount, confidence=0.7,
    )


def classify_remaining(internal_pool: list[TxnView], external_pool: list[TxnView]) -> list[ExceptionDraft]:
    internal_dupe_drafts, internal_pool = _duplicates_by_canonical_reference(internal_pool)
    external_dupe_drafts, external_pool = _duplicates_by_canonical_reference(external_pool)

    drafts = list(internal_dupe_drafts) + list(external_dupe_drafts)
    for txn in internal_pool:
        drafts.append(_classify_unmatched(txn, external_pool, "MISSING_EXTERNAL_RECORD"))
    for txn in external_pool:
        drafts.append(_classify_unmatched(txn, internal_pool, "MISSING_INTERNAL_RECORD"))
    return drafts
