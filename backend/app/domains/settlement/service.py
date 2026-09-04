"""Settlement decomposition: for a reconciled group of transactions, record
the formal gross -> deductions -> net breakdown. Reuses M4's grouping (via
reconciliation_match_transactions, already persisted) and M3's tax
calculation (via the TaxCalculation row Pass 5 already wrote) rather than
recomputing either. Distinguishes a legitimate, documented deduction from an
unexplained variance -- the latter becomes a FEE_VARIANCE exception rather
than being silently absorbed into the settlement.

Which matches get a Settlement row at all depends on *why* they matched:
- AGGREGATED / EXPLAINED_BY_FEE_TAX matches are inherently a settlement
  event -- they always get one.
- EXACT_REFERENCE / NORMALIZED_REFERENCE matches (Pass 1/2) never checked
  amount at all, so a reference-matched pair can still have a real gross/net
  gap worth explaining -- they get one only when a gap actually exists.
- AMOUNT_DATE / AMOUNT_COUNTERPARTY_DATE_INSTRUMENT matches (Pass 3/4)
  already used a configured amount tolerance as their own matching
  criterion; re-litigating that small difference here would misclassify an
  accepted matching tolerance as a financial deduction, so they never get one.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import default_clock
from app.domains.tax.service import calculate_fee_and_tax
from app.models.batch import Batch
from app.models.config_version import ClientConfiguration
from app.models.exception_ import Exception_, ExceptionEvidence, ExceptionTransaction
from app.models.reconciliation import ReconciliationMatch, ReconciliationMatchTransaction, ReconciliationRun
from app.models.settlement import Settlement, SettlementComponent
from app.models.tax import TaxCalculation
from app.models.transaction import Transaction
from app.schemas.config import ClientConfigSchema

_ROUNDING_TOLERANCE = Decimal("0.01")
_ALWAYS_SETTLE_MATCH_TYPES = ("AGGREGATED", "EXPLAINED_BY_FEE_TAX")
_SETTLE_IF_VARIANCE_MATCH_TYPES = ("EXACT_REFERENCE", "NORMALIZED_REFERENCE")


def _transactions_by_side(db: Session, match_id: str) -> tuple[list[Transaction], list[Transaction]]:
    links = list(
        db.execute(
            select(ReconciliationMatchTransaction).where(ReconciliationMatchTransaction.match_id == match_id)
        ).scalars()
    )
    source_ids = [link.transaction_id for link in links if link.side == "SOURCE"]
    target_ids = [link.transaction_id for link in links if link.side == "TARGET"]
    source_txns = [db.get(Transaction, tid) for tid in source_ids]
    target_txns = [db.get(Transaction, tid) for tid in target_ids]
    return source_txns, target_txns


def _charge_components(charges: list[dict]) -> list[dict]:
    """Turns the per-charge breakdown a fee/tax calculation recorded into
    settlement components, so a commission or an STT deduction is attributed
    by name rather than disappearing into an 'other deduction' bucket."""
    components = []
    for charge in charges or []:
        components.append({
            "component_type": "COMMISSION" if charge.get("code") == "COMMISSION" else "STATUTORY_CHARGE",
            "amount": Decimal(str(charge["amount"])),
            "description": f"{charge['label']} ({charge.get('rate_percent', '0')}% on {charge.get('basis', 'GROSS')}"
                            f"{', ' + charge['source_reference'] if charge.get('source_reference') else ''})",
            "tax_rule_id": None,
        })
    return components


def _evaluate_config_fee_rules(
    db: Session, config: ClientConfigSchema, gross_amount: Decimal, net_observed: Decimal,
    instrument_type: str | None = None,
) -> dict:
    """Applies the client's configured fee/tax treatment to a gross amount and
    reports what happened -- whether it explained the observed net or not.

    Always returns its working. An unexplained variance is the case an
    operator most needs to understand, and "no configured rule accounts for
    it" on its own does not distinguish between no rules existing, rules not
    applying to this instrument pairing, and rules applying but arriving at a
    different number. Each of those calls for a different response, so each is
    reported distinctly.
    """
    difference = gross_amount - net_observed

    if config.tax_fee_rules is None:
        return {
            "explained": False,
            "reason": "NO_RULES_CONFIGURED",
            "narrative": "This client has no fee/tax treatment configured, so no deduction could "
                         "be attributed. Configure it in the Tax & Fees window.",
            "difference": str(difference),
        }

    rules = config.tax_fee_rules
    applicable = rules.applicable_when

    # A net larger than the gross cannot be the result of deductions, however
    # they are configured -- saying so is more useful than reporting a
    # mismatch against rules that were never capable of explaining it.
    if difference < 0:
        return {
            "explained": False,
            "reason": "NET_EXCEEDS_GROSS",
            "narrative": f"The observed amount is {abs(difference)} MORE than the gross. Fees, taxes "
                         "and commissions can only reduce an amount, so no configured deduction "
                         "could produce this. Treat it as an overpayment, a credit note, or a "
                         "posting error rather than a charge.",
            "difference": str(difference),
        }

    calc = calculate_fee_and_tax(db, gross_amount, rules, instrument_type=instrument_type)
    residual = net_observed - calc.net_amount
    tolerance = Decimal(str(rules.rounding_tolerance))
    lines = [
        {"label": f"Processing fee at {calc.fee_rate_percent}%", "amount": str(calc.fee_amount),
         "verification_status": rules.fee.verification_status},
        {"label": f"{calc.tax_rule.tax_type} on fee at {calc.tax_rate_percent}%",
         "amount": str(calc.tax_amount), "verification_status": calc.tax_rule.verification_status,
         "source_reference": calc.tax_rule.source_reference},
    ] + [
        {"label": f"{line.label} at {line.rate_percent}% on {line.basis.lower()}",
         "amount": str(line.amount), "verification_status": line.verification_status,
         "source_reference": line.source_reference}
        for line in calc.charge_lines
    ]

    evaluation = {
        "applicable_when": {
            "internal_instrument_type": applicable.internal_instrument_type,
            "external_instrument_type": applicable.external_instrument_type,
        },
        "attempted_lines": lines,
        "total_deductions_if_applied": str(calc.total_deductions),
        "net_if_rules_applied": str(calc.net_amount),
        "observed_net": str(net_observed),
        "residual": str(residual),
        "rounding_tolerance": str(tolerance),
        "difference": str(difference),
    }

    if abs(residual) <= tolerance:
        evaluation.update({
            "explained": True,
            "reason": "EXPLAINED_BY_CONFIGURED_RULES",
            "narrative": f"The configured fee, tax and charges account for the full {difference}.",
            "calculation": calc,
        })
    else:
        evaluation.update({
            "explained": False,
            "reason": "RULES_PRODUCE_A_DIFFERENT_NET",
            "narrative": (
                f"The configured rules were applied and would deduct {calc.total_deductions}, giving "
                f"{calc.net_amount}. The feed reported {net_observed} instead, leaving {abs(residual)} "
                "unexplained. Either a rate here is wrong for this transaction, or the difference is "
                "not a charge at all."
            ),
        })
    return evaluation


def _components_from_calculation(calc) -> list[dict]:
    return [
        {"component_type": "FEE", "amount": calc.fee_amount, "description": "Payment-gateway processing fee",
         "tax_rule_id": None},
        {"component_type": "TAX_ON_FEE", "amount": calc.tax_amount, "description": "GST on the fee above",
         "tax_rule_id": calc.tax_rule.id},
    ] + _charge_components([line.to_dict() for line in calc.charge_lines])


def build_settlements_for_batch(db: Session, batch: Batch) -> list[Settlement]:
    latest_run = db.execute(
        select(ReconciliationRun).where(ReconciliationRun.batch_id == batch.id).order_by(ReconciliationRun.run_number.desc())
    ).scalars().first()
    if latest_run is None:
        return []

    config_row = db.get(ClientConfiguration, batch.config_version_id)
    config = ClientConfigSchema.model_validate(config_row.parsed_json)

    candidate_types = _ALWAYS_SETTLE_MATCH_TYPES + _SETTLE_IF_VARIANCE_MATCH_TYPES
    matches = list(
        db.execute(
            select(ReconciliationMatch).where(
                ReconciliationMatch.reconciliation_run_id == latest_run.id,
                ReconciliationMatch.match_type.in_(candidate_types),
            )
        ).scalars()
    )

    settlements: list[Settlement] = []
    for match in matches:
        source_txns, target_txns = _transactions_by_side(db, match.id)
        gross_amount = sum((t.amount for t in source_txns), Decimal(0))
        net_observed = sum((t.amount for t in target_txns), Decimal(0))
        diff = gross_amount - net_observed

        if match.match_type in _SETTLE_IF_VARIANCE_MATCH_TYPES and abs(diff) <= _ROUNDING_TOLERANCE:
            continue  # reference matched cleanly with no gap -- nothing to record

        components: list[dict] = []
        net_expected = gross_amount
        fully_explained = True
        evaluation: dict | None = None

        if match.match_type == "EXPLAINED_BY_FEE_TAX":
            existing = db.execute(
                select(TaxCalculation).where(TaxCalculation.reconciliation_match_id == match.id)
            ).scalar_one_or_none()
            if existing is not None:
                net_expected = existing.net_amount
                components = [
                    {"component_type": "FEE", "amount": existing.fee_amount,
                     "description": "Payment-gateway processing fee", "tax_rule_id": None},
                    {"component_type": "TAX_ON_FEE", "amount": existing.tax_amount,
                     "description": "GST on the fee above", "tax_rule_id": existing.tax_rule_id},
                ] + _charge_components((existing.calculation_detail or {}).get("charges", []))
                fully_explained = abs(net_expected - net_observed) <= _ROUNDING_TOLERANCE
        elif abs(diff) <= _ROUNDING_TOLERANCE:
            net_expected = gross_amount
            fully_explained = True
        else:
            instrument_type = source_txns[0].instrument_type if source_txns else None
            evaluation = _evaluate_config_fee_rules(
                db, config, gross_amount, net_observed, instrument_type=instrument_type
            )
            if evaluation["explained"]:
                calc = evaluation.pop("calculation")
                net_expected = calc.net_amount
                components = _components_from_calculation(calc)
                fully_explained = True
            else:
                evaluation.pop("calculation", None)
                net_expected = gross_amount
                components = [{
                    "component_type": "OTHER_DEDUCTION", "amount": diff,
                    "description": evaluation["narrative"],
                    "tax_rule_id": None,
                }]
                fully_explained = False

        detail = {
            "match_type": match.match_type,
            "source_transaction_ids": [t.id for t in source_txns],
            "target_transaction_ids": [t.id for t in target_txns],
        }
        if evaluation is not None:
            # What the configured rules were asked, and what they answered.
            # Recorded whether or not they explained the gap, so an operator
            # can tell a wrong rate from a difference that is not a charge.
            detail["fee_rule_evaluation"] = evaluation

        settlement = Settlement(
            batch_id=batch.id, reconciliation_match_id=match.id,
            gross_amount=gross_amount, net_amount_expected=net_expected, net_amount_observed=net_observed,
            is_fully_explained=fully_explained,
            detail=detail,
        )
        db.add(settlement)
        db.flush()

        for comp in components:
            db.add(SettlementComponent(
                settlement_id=settlement.id, component_type=comp["component_type"],
                amount=comp["amount"], description=comp["description"], tax_rule_id=comp.get("tax_rule_id"),
            ))

        if not fully_explained:
            _raise_fee_variance_exception(db, batch, match, source_txns + target_txns, diff)

        settlements.append(settlement)

    db.flush()
    return settlements


def _raise_fee_variance_exception(db: Session, batch: Batch, match: ReconciliationMatch,
                                   transactions: list[Transaction], amount_impact: Decimal) -> None:
    now = default_clock.now()
    primary = transactions[0]
    exception = Exception_(
        batch_id=batch.id, reconciliation_run_id=match.reconciliation_run_id, transaction_id=primary.id,
        exception_type="FEE_VARIANCE", severity="MEDIUM", status="OPEN",
        amount_impact=abs(amount_impact),
        likely_cause=f"Settlement for match {match.id} shows a gross/net variance of {amount_impact} that no "
                     "configured fee/tax rule accounts for.",
        confidence=0.6,
        recommended_action="Review the settlement's fee/tax documentation with the counterparty; "
                            "escalate if no legitimate deduction is found.",
        first_seen_at=now, last_seen_at=now,
    )
    db.add(exception)
    db.flush()
    db.add(ExceptionEvidence(
        exception_id=exception.id, evidence_type="SETTLEMENT_VARIANCE", field_name="net_amount",
        value_observed=str(amount_impact), comparator="unexplained_variance",
        detail_json={"reconciliation_match_id": match.id},
    ))
    for txn in transactions:
        db.add(ExceptionTransaction(
            exception_id=exception.id, transaction_id=txn.id,
            role="PRIMARY" if txn.id == primary.id else "RELATED",
        ))
