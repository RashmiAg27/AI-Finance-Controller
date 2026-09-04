"""Typed tools the agent calls instead of touching the database directly:
LLM -> tool function (here) -> service/query layer -> DB. Every tool returns
a plain JSON-safe dict; nothing here ever executes raw SQL handed to it by
the model, and every tool that resolves to a specific client enforces tenant
scoping via ToolContext.check_client -- a client-scoped question can never
silently pull another client's rows.
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.serialize import to_jsonable
from app.models.batch import Batch
from app.models.cash import CashForecast, CashPosition
from app.models.client import Client
from app.models.config_version import ClientConfiguration
from app.models.exception_ import Exception_, ExceptionEvidence, ExceptionTransaction
from app.models.reconciliation import MatchEvidence, ReconciliationMatch, ReconciliationMatchTransaction, ReconciliationRun
from app.models.settlement import Settlement, SettlementComponent
from app.models.tax import TaxCalculation, TaxRule
from app.models.transaction import Transaction, TransactionIdentifier
from app.schemas.config import ClientConfigSchema


class ToolScopeError(Exception):
    pass


@dataclass
class ToolContext:
    db: Session
    scope_client_id: str | None  # None = cross-client questions allowed
    actor: str = "ai-controller"

    def check_client(self, client_id: str) -> None:
        if self.scope_client_id is not None and client_id != self.scope_client_id:
            raise ToolScopeError(
                f"This question is scoped to a specific client and cannot access client_id={client_id!r}."
            )


def _needs_confirmation(action: str, plan: list[dict], question: str) -> dict:
    """The one shape every state-changing tool returns when it was called
    without an explicit confirmation.

    Confirmation is enforced here, in the tool, rather than left to the
    model's judgement: an operator must be shown exactly what is about to run
    and say yes before anything executes, and that guarantee cannot depend on
    a prompt instruction being followed.
    """
    return {
        "requires_confirmation": True,
        "action": action,
        "plan": plan,
        "ask_user": question,
        "how_to_proceed": "Call this tool again with confirmed=true once, and only once, the user has agreed.",
    }


def _batch_client_id(db: Session, batch_id: str) -> str | None:
    batch = db.get(Batch, batch_id)
    return batch.client_id if batch else None


def _transaction_client_id(db: Session, transaction_id: str) -> str | None:
    txn = db.get(Transaction, transaction_id)
    return txn.client_id if txn else None


def _match_client_id(db: Session, match_id: str) -> str | None:
    match = db.get(ReconciliationMatch, match_id)
    if match is None:
        return None
    run = db.get(ReconciliationRun, match.reconciliation_run_id)
    return _batch_client_id(db, run.batch_id) if run else None


def _exception_client_id(db: Session, exception_id: str) -> str | None:
    exc = db.get(Exception_, exception_id)
    return _batch_client_id(db, exc.batch_id) if exc else None


def _settlement_client_id(db: Session, settlement_id: str) -> str | None:
    settlement = db.get(Settlement, settlement_id)
    return _batch_client_id(db, settlement.batch_id) if settlement else None


# --------------------------------------------------------------------------
# Client / configuration
# --------------------------------------------------------------------------

def get_clients(ctx: ToolContext) -> dict:
    stmt = select(Client)
    if ctx.scope_client_id is not None:
        stmt = stmt.where(Client.id == ctx.scope_client_id)
    clients = list(ctx.db.execute(stmt).scalars())
    return {"clients": [{"id": c.id, "code": c.code, "name": c.name, "status": c.status} for c in clients]}


def get_client_configuration(ctx: ToolContext, client_id: str) -> dict:
    ctx.check_client(client_id)
    config_row = ctx.db.execute(
        select(ClientConfiguration).where(
            ClientConfiguration.client_id == client_id, ClientConfiguration.status == "ACTIVE"
        )
    ).scalar_one_or_none()
    if config_row is None:
        return {"error": f"No ACTIVE configuration for client_id={client_id!r}"}
    config = ClientConfigSchema.model_validate(config_row.parsed_json)
    return to_jsonable({
        "client_id": client_id,
        "config_version": config_row.version,
        "activated_at": config_row.activated_at,
        "data_sources": [
            {"source_id": ds.source_id, "role": ds.role, "file_format": ds.file_format,
             "identifier_priority": ds.identifier_priority}
            for ds in config.data_sources
        ],
        "identifier_linkage": [
            {"rule_id": r.rule_id, "source_identifier_type": r.source_identifier_type,
             "target_identifier_type": r.target_identifier_type, "linkage_type": r.linkage_type,
             "rationale": r.rationale}
            for r in config.identifier_linkage
        ],
        "matching_rules": [
            {"rule_id": r.rule_id, "pass": r.pass_number, "version": r.version, "confidence": r.confidence}
            for r in config.matching_rules
        ],
        "tax_fee_rules": config.tax_fee_rules.model_dump() if config.tax_fee_rules else None,
        "aggregation_rules": config.aggregation_rules.model_dump() if config.aggregation_rules else None,
    })


# --------------------------------------------------------------------------
# Batches
# --------------------------------------------------------------------------

def get_batches(ctx: ToolContext, client_id: str | None = None, status: str | None = None) -> dict:
    if client_id is not None:
        ctx.check_client(client_id)
    elif ctx.scope_client_id is not None:
        client_id = ctx.scope_client_id

    stmt = select(Batch)
    if client_id:
        stmt = stmt.where(Batch.client_id == client_id)
    if status:
        stmt = stmt.where(Batch.status == status)
    batches = list(ctx.db.execute(stmt.order_by(Batch.created_at.desc())).scalars())
    return to_jsonable({"batches": [
        {"id": b.id, "client_id": b.client_id, "batch_code": b.batch_code, "status": b.status,
         "created_at": b.created_at, "failure_reason": b.failure_reason}
        for b in batches
    ]})


def get_batch_status(ctx: ToolContext, batch_id: str) -> dict:
    client_id = _batch_client_id(ctx.db, batch_id)
    if client_id is None:
        return {"error": f"No batch found with id={batch_id!r}"}
    ctx.check_client(client_id)

    batch = ctx.db.get(Batch, batch_id)
    runs = list(ctx.db.execute(select(ReconciliationRun).where(ReconciliationRun.batch_id == batch_id)).scalars())
    return to_jsonable({
        "id": batch.id, "client_id": batch.client_id, "batch_code": batch.batch_code, "status": batch.status,
        "config_version_id": batch.config_version_id,
        "timestamps": {
            "created_at": batch.created_at, "files_received_at": batch.files_received_at,
            "validated_at": batch.validated_at, "normalized_at": batch.normalized_at,
            "reconciliation_started_at": batch.reconciliation_started_at,
            "reconciliation_completed_at": batch.reconciliation_completed_at,
            "exceptions_identified_at": batch.exceptions_identified_at,
            "closed_at": batch.closed_at,
        },
        "failure_reason": batch.failure_reason,
        "reconciliation_runs": [{"id": r.id, "run_number": r.run_number, "status": r.status, "stats": r.stats_json}
                                 for r in runs],
    })


def get_reconciliation_summary(ctx: ToolContext, batch_id: str) -> dict:
    """THE tool for "how did it go" / "brief summary" questions -- returns
    app.domains.batches.summary.ReconciliationSummary, the backend's own
    canonical account of the outcome (coverage, exception_count vs.
    affected_record_count vs. canonical_amount_at_risk already de-duplicated
    across paired exception rows, top issues, compact cash). Call
    get_batch_report instead only when the user asks for full detail,
    evidence, or an investigation of a specific issue -- never pre-emptively."""
    from dataclasses import asdict

    from app.domains.batches import summary as summary_service

    client_id = _batch_client_id(ctx.db, batch_id)
    if client_id is None:
        return {"error": f"No batch found with id={batch_id!r}"}
    ctx.check_client(client_id)

    result = summary_service.build_summary(ctx.db, batch_id)
    return to_jsonable(asdict(result))


def _count_by(items, key_fn) -> dict:
    counts: dict[str, int] = {}
    for item in items:
        k = key_fn(item)
        counts[k] = counts.get(k, 0) + 1
    return counts


# --------------------------------------------------------------------------
# Transactions / matches / evidence
# --------------------------------------------------------------------------

def get_transaction(ctx: ToolContext, transaction_id: str) -> dict:
    client_id = _transaction_client_id(ctx.db, transaction_id)
    if client_id is None:
        return {"error": f"No transaction found with id={transaction_id!r}"}
    ctx.check_client(client_id)

    txn = ctx.db.get(Transaction, transaction_id)
    identifiers = list(
        ctx.db.execute(select(TransactionIdentifier).where(TransactionIdentifier.transaction_id == transaction_id)).scalars()
    )
    match_links = list(
        ctx.db.execute(select(ReconciliationMatchTransaction).where(ReconciliationMatchTransaction.transaction_id == transaction_id)).scalars()
    )
    exception_links = list(
        ctx.db.execute(select(ExceptionTransaction).where(ExceptionTransaction.transaction_id == transaction_id)).scalars()
    )
    return to_jsonable({
        "id": txn.id, "client_id": txn.client_id, "batch_id": txn.batch_id, "source_id": txn.source_id,
        "canonical_reference": txn.canonical_reference, "transaction_type": txn.transaction_type,
        "instrument_type": txn.instrument_type, "transaction_date": txn.transaction_date,
        "value_date": txn.value_date, "amount": txn.amount, "currency": txn.currency,
        "debit_credit": txn.debit_credit, "counterparty": txn.counterparty, "description": txn.description,
        "identifiers": [{"identifier_type": i.identifier_type, "value_normalized": i.value_normalized,
                          "is_primary": i.is_primary, "linked_via_rule_id": i.linked_via_rule_id} for i in identifiers],
        "match_ids": [m.match_id for m in match_links],
        "exception_ids": [e.exception_id for e in exception_links],
        "note": "no match_ids and no exception_ids means this transaction has not been processed by "
                "reconciliation yet" if not match_links and not exception_links else None,
    })


def find_transaction_by_reference(ctx: ToolContext, client_id: str, reference: str) -> dict:
    """Looks a transaction up by canonical_reference or any identifier value
    -- users refer to 'transaction X' by a human reference, not a UUID."""
    ctx.check_client(client_id)
    reference_upper = reference.strip().upper()

    by_canonical = list(ctx.db.execute(
        select(Transaction).where(Transaction.client_id == client_id, Transaction.canonical_reference == reference_upper)
    ).scalars())
    if by_canonical:
        return to_jsonable({"matches": [{"transaction_id": t.id, "amount": t.amount, "source_id": t.source_id} for t in by_canonical]})

    by_identifier = list(ctx.db.execute(
        select(TransactionIdentifier).where(
            TransactionIdentifier.client_id == client_id, TransactionIdentifier.value_normalized == reference_upper
        )
    ).scalars())
    if by_identifier:
        return to_jsonable({"matches": [{"transaction_id": i.transaction_id, "identifier_type": i.identifier_type} for i in by_identifier]})

    return {"matches": [], "note": f"No transaction found for client_id={client_id!r} matching reference {reference!r}"}


def get_match_evidence(ctx: ToolContext, match_id: str) -> dict:
    client_id = _match_client_id(ctx.db, match_id)
    if client_id is None:
        return {"error": f"No match found with id={match_id!r}"}
    ctx.check_client(client_id)

    match = ctx.db.get(ReconciliationMatch, match_id)
    links = list(ctx.db.execute(select(ReconciliationMatchTransaction).where(ReconciliationMatchTransaction.match_id == match_id)).scalars())
    evidence = list(ctx.db.execute(select(MatchEvidence).where(MatchEvidence.match_id == match_id)).scalars())
    return to_jsonable({
        "id": match.id, "match_type": match.match_type, "cardinality": match.cardinality,
        "rule_id": match.rule_id, "rule_version": match.rule_version, "confidence": match.confidence,
        "status": match.status,
        "transactions": [{"transaction_id": l.transaction_id, "side": l.side} for l in links],
        "evidence": [{"evidence_type": e.evidence_type, "field_name": e.field_name, "source_value": e.source_value,
                      "target_value": e.target_value, "comparator": e.comparator, "detail": e.detail_json} for e in evidence],
    })


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------

def get_exception(ctx: ToolContext, exception_id: str) -> dict:
    client_id = _exception_client_id(ctx.db, exception_id)
    if client_id is None:
        return {"error": f"No exception found with id={exception_id!r}"}
    ctx.check_client(client_id)

    exc = ctx.db.get(Exception_, exception_id)
    evidence = list(ctx.db.execute(select(ExceptionEvidence).where(ExceptionEvidence.exception_id == exception_id)).scalars())
    txns = list(ctx.db.execute(select(ExceptionTransaction).where(ExceptionTransaction.exception_id == exception_id)).scalars())
    return to_jsonable({
        "id": exc.id, "batch_id": exc.batch_id, "exception_type": exc.exception_type, "severity": exc.severity,
        "status": exc.status, "amount_impact": exc.amount_impact, "likely_cause": exc.likely_cause,
        "confidence": exc.confidence, "recommended_action": exc.recommended_action,
        "first_seen_at": exc.first_seen_at, "last_seen_at": exc.last_seen_at,
        "transactions": [{"transaction_id": t.transaction_id, "role": t.role} for t in txns],
        "evidence": [{"evidence_type": e.evidence_type, "field_name": e.field_name, "value_observed": e.value_observed,
                      "detail": e.detail_json} for e in evidence],
    })


def get_exception_summary(ctx: ToolContext, batch_id: str, top_n: int = 10) -> dict:
    client_id = _batch_client_id(ctx.db, batch_id)
    if client_id is None:
        return {"error": f"No batch found with id={batch_id!r}"}
    ctx.check_client(client_id)

    exceptions = list(
        ctx.db.execute(select(Exception_).where(Exception_.batch_id == batch_id, Exception_.status == "OPEN")).scalars()
    )
    largest = sorted(exceptions, key=lambda e: (e.amount_impact or 0), reverse=True)[:top_n]
    return to_jsonable({
        "batch_id": batch_id, "open_exception_count": len(exceptions),
        "by_type": _count_by(exceptions, lambda e: e.exception_type),
        "by_severity": _count_by(exceptions, lambda e: e.severity),
        "largest_exceptions": [
            {"id": e.id, "exception_type": e.exception_type, "amount_impact": e.amount_impact,
             "likely_cause": e.likely_cause, "transaction_id": e.transaction_id}
            for e in largest
        ],
    })


# --------------------------------------------------------------------------
# Tax / settlement
# --------------------------------------------------------------------------

def get_tax_rule(ctx: ToolContext, rule_id: str) -> dict:
    rule = ctx.db.execute(select(TaxRule).where(TaxRule.rule_id == rule_id)).scalar_one_or_none()
    if rule is None:
        return {"error": f"No tax rule found with rule_id={rule_id!r}"}
    return to_jsonable({
        "rule_id": rule.rule_id, "rule_version": rule.rule_version, "tax_type": rule.tax_type,
        "calculation_basis": rule.calculation_basis, "rate_percent": rule.rate_percent,
        "effective_from": rule.effective_from, "effective_to": rule.effective_to,
        "applicability": rule.applicability, "source_authority": rule.source_authority,
        "source_reference": rule.source_reference, "source_url": rule.source_url,
        "verification_status": rule.verification_status, "verification_note": rule.verification_note,
    })


def get_tax_calculation(ctx: ToolContext, match_id: str) -> dict:
    client_id = _match_client_id(ctx.db, match_id)
    if client_id is None:
        return {"error": f"No match found with id={match_id!r}"}
    ctx.check_client(client_id)

    calc = ctx.db.execute(select(TaxCalculation).where(TaxCalculation.reconciliation_match_id == match_id)).scalar_one_or_none()
    if calc is None:
        return {"error": f"No tax calculation is associated with match_id={match_id!r} "
                          "(this match wasn't resolved via the tax/fee-explained pass)."}
    rule = ctx.db.get(TaxRule, calc.tax_rule_id)
    return to_jsonable({
        "match_id": match_id, "gross_amount": calc.gross_amount, "fee_amount": calc.fee_amount,
        "taxable_amount": calc.taxable_amount, "tax_amount": calc.tax_amount, "net_amount": calc.net_amount,
        "tax_rule": {"rule_id": rule.rule_id, "rate_percent": rule.rate_percent,
                     "source_reference": rule.source_reference, "verification_status": rule.verification_status},
    })


def get_settlement(ctx: ToolContext, match_id: str) -> dict:
    client_id = _match_client_id(ctx.db, match_id)
    if client_id is None:
        return {"error": f"No match found with id={match_id!r}"}
    ctx.check_client(client_id)

    settlement = ctx.db.execute(select(Settlement).where(Settlement.reconciliation_match_id == match_id)).scalar_one_or_none()
    if settlement is None:
        return {"error": f"No settlement decomposition exists for match_id={match_id!r}."}
    components = list(ctx.db.execute(select(SettlementComponent).where(SettlementComponent.settlement_id == settlement.id)).scalars())
    return to_jsonable({
        "id": settlement.id, "gross_amount": settlement.gross_amount,
        "net_amount_expected": settlement.net_amount_expected, "net_amount_observed": settlement.net_amount_observed,
        "is_fully_explained": settlement.is_fully_explained,
        "components": [{"type": c.component_type, "amount": c.amount, "description": c.description} for c in components],
    })


# --------------------------------------------------------------------------
# Cash / forecast
# --------------------------------------------------------------------------

def get_cash_position(ctx: ToolContext, client_id: str) -> dict:
    ctx.check_client(client_id)
    position = ctx.db.execute(
        select(CashPosition).where(CashPosition.client_id == client_id).order_by(CashPosition.created_at.desc())
    ).scalars().first()
    if position is None:
        return {"error": f"No cash position has been computed yet for client_id={client_id!r}."}
    return to_jsonable({
        "as_of": position.as_of, "confirmed_cash": position.confirmed_cash, "pending_cash": position.pending_cash,
        "expected_inflows": position.expected_inflows, "expected_outflows": position.expected_outflows,
        "unreconciled_amount": position.unreconciled_amount,
        "note": "confirmed_cash reflects only CONFIRMED matches against external (bank/gateway) transactions; "
                "unreconciled_amount is the total amount currently at risk across all open exceptions.",
    })


def get_forecast(ctx: ToolContext, client_id: str) -> dict:
    ctx.check_client(client_id)
    forecast = ctx.db.execute(
        select(CashForecast).where(CashForecast.client_id == client_id).order_by(CashForecast.created_at.desc())
    ).scalars().first()
    if forecast is None:
        return {"error": f"No cash forecast has been computed yet for client_id={client_id!r}."}
    return to_jsonable({
        "horizon_days": forecast.horizon_days, "as_of": forecast.as_of, "expected_value": forecast.expected_value,
        "low_estimate": forecast.low_estimate, "high_estimate": forecast.high_estimate,
        "drivers": forecast.drivers, "assumptions_note": forecast.assumptions_note,
    })


# --------------------------------------------------------------------------
# Configured batches, import sources, and running them
#
# Everything below this line can change the state of the system. Each such
# tool refuses to act until it is called with confirmed=true, and returns the
# exact plan it would execute so the agent can put that plan to the user
# first. Read-only tools above never require confirmation.
# --------------------------------------------------------------------------

def list_batch_definitions(ctx: ToolContext, client_id: str) -> dict:
    """The configured batches for a client, with the live state the
    Reconciliation window shows: whether their data has arrived, where it
    comes from, and how the last run ended."""
    ctx.check_client(client_id)
    from app.domains.batches import definitions as definitions_service

    from app.domains.reconciliation import types as recon_types
    from app.models.bank_account import BankAccount

    rows = definitions_service.list_definitions(ctx.db, client_id)
    out = []
    for definition in rows:
        state = definitions_service.definition_state(ctx.db, definition)
        latest = state["latest_batch"]
        rtype = recon_types.describe(definition.reconciliation_type)
        account = ctx.db.get(BankAccount, definition.bank_account_id) if definition.bank_account_id else None
        out.append({
            "batch_definition_id": definition.id, "code": definition.code, "name": definition.name,
            # What this cycle PROVES. Distinct from batch_type, which is only a
            # scheduling label -- reporting the latter as the reconciliation
            # type would misdescribe what the batch actually checks.
            "reconciliation_type": definition.reconciliation_type,
            "reconciliation_label": rtype["label"],
            "compares": f"{rtype.get('left_side')} against {rtype.get('right_side')}",
            "legitimate_differences": rtype.get("legitimate_differences"),
            # WHICH account it proves it for.
            "bank_account": {
                "bank_account_id": account.id, "account_code": account.account_code,
                "bank": account.bank_name, "account_number": account.account_number_masked,
                "purpose": account.purpose,
            } if account else None,
            "scope_note": None if account else
                "This cycle is not scoped to a single account -- it spans accounts by nature.",
            "batch_type": definition.batch_type, "trigger_type": definition.trigger_type,
            "trigger_detail": definition.trigger_detail, "enabled": definition.enabled,
            "source_ids": list(definition.source_ids or []),
            "import_location": state["import_location"],
            "state": state["state"], "data_available": state["data_available"],
            "missing_source_ids": state["missing_source_ids"],
            "latest_run": {
                "batch_id": latest.id, "batch_code": latest.batch_code, "status": latest.status,
                "progress_pct": latest.progress_pct, "current_stage": latest.current_stage,
                "failure_reason": latest.failure_reason,
            } if latest is not None else None,
        })
    return to_jsonable({"client_id": client_id, "batch_definitions": out})


def get_import_sources(ctx: ToolContext, client_id: str) -> dict:
    ctx.check_client(client_id)
    from app.domains.batches import definitions as definitions_service
    from app.domains.ingestion import import_sources as import_sources_domain

    client = ctx.db.get(Client, client_id)
    rows = definitions_service.list_import_sources(ctx.db, client_id)
    return to_jsonable({"client_id": client_id, "import_sources": [
        {"import_source_id": r.id, "code": r.code, "name": r.name, "kind": r.kind, "enabled": r.enabled,
         "location": import_sources_domain.describe_location(r, client.code),
         "connection": dict(r.connection_json or {}),
         "last_status": r.last_status, "last_message": r.last_message}
        for r in rows
    ]})


def get_batch_log(ctx: ToolContext, batch_id: str, level: str | None = None, limit: int = 60) -> dict:
    """The operator-facing run log, including every exception in full. This is
    where the reason a run failed actually lives."""
    client_id = _batch_client_id(ctx.db, batch_id)
    if client_id is None:
        return {"error": f"No batch found with id={batch_id!r}"}
    ctx.check_client(client_id)

    from app.domains.batches import run_log

    entries = run_log.entries(ctx.db, batch_id)
    if level:
        entries = [e for e in entries if e.level == level.upper()]
    truncated = len(entries) > limit
    return to_jsonable({
        "batch_id": batch_id, "entry_count": len(entries), "truncated": truncated,
        "entries": [{"seq": e.seq, "at": e.created_at, "level": e.level, "stage": e.stage,
                     "message": e.message, "detail": e.detail_json} for e in entries[-limit:]],
    })


def get_batch_report(ctx: ToolContext, batch_id: str) -> dict:
    """The FULL result of a run: every match, every exception with its raw
    evidence, settlement decomposition, and cash position. This is detail/
    investigation-mode data, not what a summary question needs -- call
    get_reconciliation_summary for 'how did it go' / 'brief summary', and
    reach for this one only once the user has asked for detail, evidence,
    or to investigate a specific issue."""
    client_id = _batch_client_id(ctx.db, batch_id)
    if client_id is None:
        return {"error": f"No batch found with id={batch_id!r}"}
    ctx.check_client(client_id)

    from app.domains.batches import report

    result = report.build(ctx.db, batch_id, include_log=False)
    result["ui"] = {"open": "batch", "client_id": client_id, "batch_id": batch_id}
    return to_jsonable(result)


def run_batch(ctx: ToolContext, batch_definition_id: str, confirmed: bool = False) -> dict:
    """Runs ONE configured batch. Refuses until confirmed=true."""
    from app.domains.batches import definitions as definitions_service, runner, service as batch_service

    definition = ctx.db.get(_batch_definition_model(), batch_definition_id)
    if definition is None:
        return {"error": f"No batch definition found with id={batch_definition_id!r}. "
                          "Call list_batch_definitions first to get valid ids."}
    ctx.check_client(definition.client_id)

    state = definitions_service.definition_state(ctx.db, definition)
    plan = [{
        "batch_definition_id": definition.id, "code": definition.code, "name": definition.name,
        "import_location": state["import_location"], "state": state["state"],
        "data_available": state["data_available"], "missing_source_ids": state["missing_source_ids"],
    }]
    if not confirmed:
        return _needs_confirmation(
            "run_batch", plan,
            f"Run the {definition.name} batch ({definition.code}) now?",
        )
    if not definition.enabled:
        return {"error": f"batch definition {definition.code!r} is disabled and cannot be run; "
                          "enable it in the Reconciliation window first."}

    business_date = definitions_service.next_business_date(ctx.db, definition)
    batch = batch_service.create_batch(
        ctx.db, client_id=definition.client_id,
        batch_code=definitions_service.next_batch_code(ctx.db, definition, business_date),
        actor=ctx.actor, batch_definition_id=definition.id, business_date=business_date,
        triggered_by_type="AGENT",
    )
    ctx.db.commit()
    runner.submit(batch.id)
    return to_jsonable({
        "started": True, "batch_id": batch.id, "batch_code": batch.batch_code,
        "batch_definition_code": definition.code, "status": batch.status,
        "note": "The run executes in the background. Poll get_batch_status or get_batch_log for progress; "
                "it is not finished at the moment this tool returns.",
        "ui": {"open": "reconciliation", "client_id": definition.client_id, "batch_id": batch.id},
    })


def run_all_batches(ctx: ToolContext, client_id: str, batch_definition_codes: list[str] | None = None,
                    confirmed: bool = False) -> dict:
    """Runs every enabled configured batch for a client, or just the named
    subset. Refuses until confirmed=true."""
    ctx.check_client(client_id)
    from app.domains.batches import definitions as definitions_service, runner, service as batch_service

    definitions = definitions_service.list_definitions(ctx.db, client_id)
    if batch_definition_codes:
        wanted = {c.upper() for c in batch_definition_codes}
        definitions = [d for d in definitions if d.code.upper() in wanted or d.id in batch_definition_codes]
        if not definitions:
            return {"error": f"none of {batch_definition_codes} match a configured batch for this client"}

    runnable = [d for d in definitions if d.enabled]
    plan = []
    for definition in runnable:
        state = definitions_service.definition_state(ctx.db, definition)
        plan.append({"batch_definition_id": definition.id, "code": definition.code, "name": definition.name,
                     "state": state["state"], "data_available": state["data_available"],
                     "import_location": state["import_location"]})

    if not confirmed:
        return _needs_confirmation(
            "run_all_batches", plan,
            f"Run all {len(runnable)} enabled batch(es) for this client, or would you like a specific one?",
        )

    queued, skipped = [], []
    for definition in runnable:
        business_date = definitions_service.next_business_date(ctx.db, definition)
        try:
            batch = batch_service.create_batch(
                ctx.db, client_id=client_id,
                batch_code=definitions_service.next_batch_code(ctx.db, definition, business_date),
                actor=ctx.actor, batch_definition_id=definition.id, business_date=business_date,
                triggered_by_type="AGENT",
            )
            ctx.db.commit()
            runner.submit(batch.id)
            queued.append({"batch_definition_code": definition.code, "batch_id": batch.id,
                           "batch_code": batch.batch_code})
        except Exception as exc:  # noqa: BLE001 -- one failure must not block the rest
            ctx.db.rollback()
            skipped.append({"batch_definition_code": definition.code, "reason": str(exc)})

    for definition in definitions:
        if not definition.enabled:
            skipped.append({"batch_definition_code": definition.code, "reason": "disabled"})

    return to_jsonable({
        "started": True, "queued": queued, "skipped": skipped,
        "note": "Runs execute one after another in the background. Poll get_batch_status or "
                "list_batch_definitions for progress.",
        "ui": {"open": "reconciliation", "client_id": client_id,
               "batch_id": queued[0]["batch_id"] if queued else None},
    })


def update_import_source(ctx: ToolContext, import_source_id: str, connection: dict | None = None,
                         enabled: bool | None = None, kind: str | None = None,
                         confirmed: bool = False) -> dict:
    """Changes where a batch's files are fetched from. Refuses until
    confirmed=true, because it silently redirects a production feed."""
    from app.domains.batches import definitions as definitions_service

    row = ctx.db.get(_import_source_model(), import_source_id)
    if row is None:
        return {"error": f"No import source found with id={import_source_id!r}"}
    ctx.check_client(row.client_id)

    patch: dict = {}
    if connection is not None:
        patch["connection_json"] = connection
    if enabled is not None:
        patch["enabled"] = enabled
    if kind is not None:
        patch["kind"] = kind
    if not patch:
        return {"error": "nothing to change: pass connection, kind, and/or enabled"}

    if not confirmed:
        return _needs_confirmation(
            "update_import_source",
            [{"import_source_id": row.id, "code": row.code, "current_kind": row.kind,
              "current_connection": dict(row.connection_json or {}), "proposed_change": patch}],
            f"Change the '{row.name}' import source as described?",
        )

    try:
        updated = definitions_service.update_import_source(ctx.db, import_source_id, patch, actor=ctx.actor)
        ctx.db.commit()
    except Exception as exc:  # noqa: BLE001 -- report the validation message, don't crash the turn
        ctx.db.rollback()
        return {"error": str(exc)}

    probe = definitions_service.probe_import_source(ctx.db, import_source_id)
    ctx.db.commit()
    return to_jsonable({
        "updated": True, "import_source_id": updated.id, "kind": updated.kind,
        "connection": dict(updated.connection_json or {}),
        "probe": probe,
        "ui": {"open": "reconciliation", "client_id": updated.client_id},
    })


def _batch_definition_model():
    from app.models.batch_definition import BatchDefinition

    return BatchDefinition


def _import_source_model():
    from app.models.import_source import ImportSource

    return ImportSource


from app.agent import analysis_tools as _analysis

TOOL_REGISTRY = {
    "get_clients": get_clients,
    "list_reconciliation_types": _analysis.list_reconciliation_types,
    "get_bank_accounts": _analysis.get_bank_accounts,
    "get_account_position": _analysis.get_account_position,
    "explain_amount_difference": _analysis.explain_amount_difference,
    "search_transactions": _analysis.search_transactions,
    "aggregate_exceptions": _analysis.aggregate_exceptions,
    "list_batch_definitions": list_batch_definitions,
    "get_import_sources": get_import_sources,
    "get_batch_log": get_batch_log,
    "get_batch_report": get_batch_report,
    "run_batch": run_batch,
    "run_all_batches": run_all_batches,
    "update_import_source": update_import_source,
    "get_client_configuration": get_client_configuration,
    "get_batches": get_batches,
    "get_batch_status": get_batch_status,
    "get_reconciliation_summary": get_reconciliation_summary,
    "get_transaction": get_transaction,
    "find_transaction_by_reference": find_transaction_by_reference,
    "get_match_evidence": get_match_evidence,
    "get_exception": get_exception,
    "get_exception_summary": get_exception_summary,
    "get_tax_rule": get_tax_rule,
    "get_tax_calculation": get_tax_calculation,
    "get_settlement": get_settlement,
    "get_cash_position": get_cash_position,
    "get_forecast": get_forecast,
}


def execute_tool(ctx: ToolContext, name: str, tool_input: dict) -> dict:
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name!r}"}
    try:
        return fn(ctx, **tool_input)
    except ToolScopeError as exc:
        return {"error": str(exc)}
    except TypeError as exc:
        return {"error": f"Invalid arguments for tool {name!r}: {exc}"}
