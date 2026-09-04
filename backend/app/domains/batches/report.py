"""The complete account of one batch run.

Built once, in one place, and read by both the Reconciliation window and the
agent -- so what the agent tells a user about a run and what the screen shows
them cannot disagree. Every number here is read back from persisted results;
nothing is recomputed or estimated.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domains.batches import run_log
from app.models.batch import Batch, BatchFile
from app.models.batch_definition import BatchDefinition
from app.models.cash import CashForecast, CashPosition
from app.models.exception_ import Exception_, ExceptionTransaction
from app.models.reconciliation import ReconciliationMatch, ReconciliationRun
from app.models.settlement import Settlement, SettlementComponent
from app.models.source_file import SourceFile
from app.models.transaction import Transaction


def _count_by(items, key_fn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = key_fn(item)
        counts[key] = counts.get(key, 0) + 1
    return counts


def build(db: Session, batch_id: str, *, include_log: bool = True) -> dict:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise NotFoundError("Batch", batch_id)

    definition = db.get(BatchDefinition, batch.batch_definition_id) if batch.batch_definition_id else None

    transactions = list(db.execute(select(Transaction).where(Transaction.batch_id == batch_id)).scalars())
    by_source = _count_by(transactions, lambda t: t.source_id)

    run = db.execute(
        select(ReconciliationRun).where(ReconciliationRun.batch_id == batch_id)
        .order_by(ReconciliationRun.run_number.desc())
    ).scalars().first()
    matches = list(db.execute(
        select(ReconciliationMatch).where(ReconciliationMatch.reconciliation_run_id == run.id)
    ).scalars()) if run else []

    exceptions = list(db.execute(select(Exception_).where(Exception_.batch_id == batch_id)).scalars())
    open_exceptions = [e for e in exceptions if e.status == "OPEN"]

    settlements = list(db.execute(select(Settlement).where(Settlement.batch_id == batch_id)).scalars())
    unexplained = [s for s in settlements if not s.is_fully_explained]

    files = []
    for bf in db.execute(select(BatchFile).where(BatchFile.batch_id == batch_id)).scalars():
        source_file = db.get(SourceFile, bf.source_file_id)
        if source_file is not None:
            files.append({
                "filename": source_file.original_filename, "file_format": source_file.file_format,
                "size_bytes": source_file.size_bytes, "checksum_sha256": source_file.checksum_sha256,
            })

    position = db.execute(
        select(CashPosition).where(CashPosition.client_id == batch.client_id)
        .order_by(CashPosition.created_at.desc())
    ).scalars().first()
    forecast = db.execute(
        select(CashForecast).where(CashForecast.client_id == batch.client_id)
        .order_by(CashForecast.created_at.desc())
    ).scalars().first()

    matched_txn_count = sum(len(_match_transaction_ids(db, m.id)) for m in matches)
    total_txns = len(transactions)

    report = {
        "batch": {
            "id": batch.id, "batch_code": batch.batch_code, "client_id": batch.client_id,
            "status": batch.status, "current_stage": batch.current_stage, "progress_pct": batch.progress_pct,
            "business_date": batch.business_date, "triggered_by": batch.triggered_by,
            "triggered_by_type": batch.triggered_by_type,
            "created_at": batch.created_at, "closed_at": batch.closed_at,
            "failure_reason": batch.failure_reason,
            "batch_definition_id": batch.batch_definition_id,
            "batch_definition_code": definition.code if definition else None,
            "batch_definition_name": definition.name if definition else None,
        },
        "files": files,
        "transactions": {"total": total_txns, "by_source": by_source},
        "reconciliation": {
            "run_id": run.id if run else None,
            "run_status": run.status if run else None,
            "stats": dict(run.stats_json or {}) if run else {},
            "match_count": len(matches),
            "matches_by_type": _count_by(matches, lambda m: m.match_type),
            "matches_by_cardinality": _count_by(matches, lambda m: m.cardinality),
            "matched_transaction_count": matched_txn_count,
            "match_rate_pct": round(100 * matched_txn_count / total_txns, 1) if total_txns else None,
        },
        "exceptions": {
            "total": len(exceptions),
            "open": len(open_exceptions),
            "by_type": _count_by(exceptions, lambda e: e.exception_type),
            "by_severity": _count_by(exceptions, lambda e: e.severity),
            "total_amount_at_risk": str(sum((e.amount_impact for e in open_exceptions if e.amount_impact),
                                            Decimal(0))),
            "items": [_exception_detail(db, e) for e in sorted(
                exceptions, key=lambda e: (e.amount_impact or Decimal(0)), reverse=True)],
        },
        "settlements": {
            "total": len(settlements),
            "unexplained": len(unexplained),
            "components": [_settlement_detail(db, s) for s in settlements],
        },
        "cash": {
            "as_of": position.as_of if position else None,
            "confirmed_cash": str(position.confirmed_cash) if position else None,
            "pending_cash": str(position.pending_cash) if position else None,
            "expected_inflows": str(position.expected_inflows) if position else None,
            "expected_outflows": str(position.expected_outflows) if position else None,
            "unreconciled_amount": str(position.unreconciled_amount) if position else None,
            "forecast": {
                "horizon_days": forecast.horizon_days, "as_of": forecast.as_of,
                "expected_value": str(forecast.expected_value),
                "low_estimate": str(forecast.low_estimate), "high_estimate": str(forecast.high_estimate),
                "drivers": forecast.drivers, "assumptions_note": forecast.assumptions_note,
            } if forecast else None,
        },
    }

    if include_log:
        report["log"] = [
            {"seq": e.seq, "created_at": e.created_at, "level": e.level, "stage": e.stage,
             "message": e.message, "detail": e.detail_json}
            for e in run_log.entries(db, batch_id)
        ]
    return report


def _match_transaction_ids(db: Session, match_id: str) -> list[str]:
    from app.models.reconciliation import ReconciliationMatchTransaction

    return list(db.execute(
        select(ReconciliationMatchTransaction.transaction_id)
        .where(ReconciliationMatchTransaction.match_id == match_id)
    ).scalars())


def _exception_detail(db: Session, exc: Exception_) -> dict:
    txn_ids = list(db.execute(
        select(ExceptionTransaction.transaction_id).where(ExceptionTransaction.exception_id == exc.id)
    ).scalars())
    transactions = []
    for txn_id in txn_ids:
        txn = db.get(Transaction, txn_id)
        if txn is not None:
            transactions.append({
                "transaction_id": txn.id, "source_id": txn.source_id,
                "reference": txn.canonical_reference, "amount": str(txn.amount),
                "currency": txn.currency, "counterparty": txn.counterparty,
                "transaction_date": str(txn.transaction_date), "description": txn.description,
            })
    return {
        "id": exc.id, "exception_type": exc.exception_type, "severity": exc.severity, "status": exc.status,
        "amount_impact": str(exc.amount_impact) if exc.amount_impact is not None else None,
        "likely_cause": exc.likely_cause, "confidence": exc.confidence,
        "recommended_action": exc.recommended_action, "transactions": transactions,
    }


def _settlement_detail(db: Session, settlement: Settlement) -> dict:
    components = list(db.execute(
        select(SettlementComponent).where(SettlementComponent.settlement_id == settlement.id)
    ).scalars())
    detail = settlement.detail or {}
    return {
        "id": settlement.id, "gross_amount": str(settlement.gross_amount),
        "net_amount_expected": str(settlement.net_amount_expected),
        "net_amount_observed": str(settlement.net_amount_observed),
        "is_fully_explained": settlement.is_fully_explained,
        "match_type": detail.get("match_type"),
        # What the configured fee/tax rules were asked and what they answered.
        # Present even when they failed -- that is when it matters most.
        "fee_rule_evaluation": detail.get("fee_rule_evaluation"),
        "components": [{"type": c.component_type, "amount": str(c.amount), "description": c.description}
                       for c in components],
    }
