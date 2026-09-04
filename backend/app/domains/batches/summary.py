"""A canonical, backend-computed reconciliation summary -- the model behind
"how did it go", built so the agent presents a business outcome the backend
itself computed, never one assembled or aggregated by an LLM (get_batch_report
still exists, in app.domains.batches.report, for full detail/investigation).

Exception rows can legitimately double up on the same underlying issue by
construction (see app.domains.exceptions.classifier -- a duplicate pair or a
near-miss classified independently from both sides produces one Exception_
row PER SIDE, each carrying the full amount, linked to each other via
ExceptionTransaction). Summing every row's amount_impact would silently
double the true amount at risk for exactly the transactions that matter
most. This module is where "one exception, how many records, how much
money" gets decided once, so nothing downstream -- least of all an LLM --
has to re-derive it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.batch import Batch
from app.models.batch_definition import BatchDefinition
from app.models.cash import CashPosition
from app.models.exception_ import Exception_, ExceptionTransaction
from app.models.reconciliation import ReconciliationMatch, ReconciliationMatchTransaction, ReconciliationRun
from app.models.transaction import Transaction


@dataclass
class IssueGroup:
    """One logical problem, however many Exception_ rows or transactions it
    touches -- the unit a finance analyst actually cares about, not the unit
    the database happens to store one per side of."""

    exception_type: str
    severity: str
    amount_impact: Decimal | None
    affected_record_count: int
    likely_cause: str | None
    recommended_action: str | None


@dataclass
class ReconciliationSummary:
    client_id: str
    batch_id: str
    # Evidence-only fields -- a finance analyst never sees these led with;
    # they exist for a "show details"/"show evidence" follow-up.
    batch_reference: str
    batch_name: str
    status: str
    business_date: str | None
    completed_at: datetime | None

    records_processed: int
    resolved_count: int
    coverage_pct: float | None

    exception_count: int
    affected_record_count: int
    canonical_amount_at_risk: Decimal

    top_issues: list[IssueGroup]

    confirmed_cash: Decimal | None
    pending_cash: Decimal | None
    unreconciled_amount: Decimal | None


def _group_open_exceptions(db: Session, exceptions: list[Exception_]) -> list[IssueGroup]:
    """Collapses exception rows that reference the same transaction(s) --
    via ExceptionTransaction -- into one IssueGroup. Two rows sharing a
    transaction are, by how the classifier works today, always the two
    sides of the SAME underlying problem (a duplicate pair, or a near-miss
    classified independently from both sides), never two unrelated
    problems that happen to touch the same record -- so grouping on shared
    transactions is a safe proxy for "same issue" given the current engine.
    """
    if not exceptions:
        return []

    by_id = {e.id: e for e in exceptions}
    links = list(db.execute(
        select(ExceptionTransaction.exception_id, ExceptionTransaction.transaction_id)
        .where(ExceptionTransaction.exception_id.in_(by_id))
    ))
    txns_by_exception: dict[str, set[str]] = {}
    exceptions_by_txn: dict[str, set[str]] = {}
    for exception_id, transaction_id in links:
        txns_by_exception.setdefault(exception_id, set()).add(transaction_id)
        exceptions_by_txn.setdefault(transaction_id, set()).add(exception_id)

    # Union-find over "these two exception rows share a transaction".
    parent: dict[str, str] = {e.id: e.id for e in exceptions}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for exception_ids in exceptions_by_txn.values():
        ids = list(exception_ids)
        for other in ids[1:]:
            union(ids[0], other)

    groups: dict[str, list[Exception_]] = {}
    for e in exceptions:
        groups.setdefault(find(e.id), []).append(e)

    result: list[IssueGroup] = []
    for members in groups.values():
        affected: set[str] = set()
        for m in members:
            affected |= txns_by_exception.get(m.id, {m.transaction_id})
        # One representative amount for the group, not a sum across its
        # rows -- each row in a duplicate/near-miss pair carries the SAME
        # financial exposure, not an additional one.
        representative = max(members, key=lambda m: m.amount_impact or Decimal(0))
        result.append(IssueGroup(
            exception_type=representative.exception_type,
            severity=representative.severity,
            amount_impact=representative.amount_impact,
            affected_record_count=len(affected) or len(members),
            likely_cause=representative.likely_cause,
            recommended_action=representative.recommended_action,
        ))

    result.sort(key=lambda g: (g.amount_impact or Decimal(0)), reverse=True)
    return result


def build_summary(db: Session, batch_id: str) -> ReconciliationSummary:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise NotFoundError("Batch", batch_id)

    definition = db.get(BatchDefinition, batch.batch_definition_id) if batch.batch_definition_id else None

    transaction_ids = list(db.execute(select(Transaction.id).where(Transaction.batch_id == batch_id)).scalars())
    records_processed = len(transaction_ids)

    run = db.execute(
        select(ReconciliationRun).where(ReconciliationRun.batch_id == batch_id)
        .order_by(ReconciliationRun.run_number.desc())
    ).scalars().first()
    matched_ids: set[str] = set()
    if run is not None:
        match_ids = list(db.execute(
            select(ReconciliationMatch.id).where(ReconciliationMatch.reconciliation_run_id == run.id)
        ).scalars())
        if match_ids:
            matched_ids = set(db.execute(
                select(ReconciliationMatchTransaction.transaction_id)
                .where(ReconciliationMatchTransaction.match_id.in_(match_ids))
            ).scalars())
    resolved_count = len(matched_ids)
    coverage_pct = round(100 * resolved_count / records_processed, 1) if records_processed else None

    open_exceptions = list(db.execute(
        select(Exception_).where(Exception_.batch_id == batch_id, Exception_.status == "OPEN")
    ).scalars())
    issue_groups = _group_open_exceptions(db, open_exceptions)
    exception_count = len(issue_groups)
    affected_record_count = sum(g.affected_record_count for g in issue_groups)
    canonical_amount_at_risk = sum((g.amount_impact or Decimal(0) for g in issue_groups), Decimal(0))

    position = db.execute(
        select(CashPosition).where(CashPosition.client_id == batch.client_id)
        .order_by(CashPosition.created_at.desc())
    ).scalars().first()

    return ReconciliationSummary(
        client_id=batch.client_id,
        batch_id=batch.id,
        batch_reference=batch.batch_code,
        batch_name=definition.name if definition else batch.batch_code,
        status=batch.status,
        business_date=batch.business_date,
        completed_at=batch.closed_at,
        records_processed=records_processed,
        resolved_count=resolved_count,
        coverage_pct=coverage_pct,
        exception_count=exception_count,
        affected_record_count=affected_record_count,
        canonical_amount_at_risk=canonical_amount_at_risk,
        top_issues=issue_groups[:5],
        confirmed_cash=position.confirmed_cash if position else None,
        pending_cash=position.pending_cash if position else None,
        unreconciled_amount=position.unreconciled_amount if position else None,
    )
