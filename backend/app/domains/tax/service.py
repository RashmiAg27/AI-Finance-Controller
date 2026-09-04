from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domains.normalization.value_normalizers import round_decimal
from app.models.tax import TaxRule
from app.schemas.config import StatutoryChargeConfig, TaxFeeRules

_HUNDRED = Decimal(100)


@dataclass
class ChargeLine:
    """One deduction that is neither the gateway fee nor the tax on it --
    a commission, or a statutory levy such as STT or stamp duty. Carries its
    own basis and provenance so a settlement can be explained line by line."""

    code: str
    label: str
    basis: str
    rate_percent: Decimal
    amount: Decimal
    verification_status: str
    source_authority: str | None = None
    source_reference: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code, "label": self.label, "basis": self.basis,
            "rate_percent": str(self.rate_percent), "amount": str(self.amount),
            "verification_status": self.verification_status,
            "source_authority": self.source_authority, "source_reference": self.source_reference,
        }


@dataclass
class FeeTaxCalculation:
    gross_amount: Decimal
    fee_amount: Decimal
    fee_rate_percent: Decimal
    tax_amount: Decimal
    tax_rate_percent: Decimal
    net_amount: Decimal
    tax_rule: TaxRule
    charge_lines: list[ChargeLine] = field(default_factory=list)

    @property
    def charges_total(self) -> Decimal:
        return sum((line.amount for line in self.charge_lines), Decimal(0))

    @property
    def total_deductions(self) -> Decimal:
        return self.fee_amount + self.tax_amount + self.charges_total


def get_tax_rule(db: Session, rule_id: str) -> TaxRule:
    rule = db.execute(select(TaxRule).where(TaxRule.rule_id == rule_id)).scalar_one_or_none()
    if rule is None:
        raise NotFoundError("TaxRule", rule_id)
    return rule


def _charge_basis_amount(basis: str, *, gross: Decimal, fee: Decimal, tax: Decimal) -> Decimal:
    if basis == "FEE":
        return fee
    if basis == "FEE_PLUS_TAX":
        return fee + tax
    return gross


def _statutory_charge_line(charge: StatutoryChargeConfig, *, gross: Decimal, fee: Decimal,
                           tax: Decimal, instrument_type: str | None) -> ChargeLine | None:
    if not charge.enabled:
        return None
    if charge.applies_to_instrument_types and instrument_type not in charge.applies_to_instrument_types:
        return None

    basis_amount = _charge_basis_amount(charge.basis, gross=gross, fee=fee, tax=tax)
    rate = Decimal(str(charge.rate_percent))
    amount = round_decimal(basis_amount * rate / _HUNDRED, 2, "HALF_UP") + Decimal(str(charge.flat_amount))
    if amount == 0:
        return None
    return ChargeLine(
        code=charge.code, label=charge.label, basis=charge.basis, rate_percent=rate,
        amount=round_decimal(amount, 2, "HALF_UP"), verification_status=charge.verification_status,
        source_authority=charge.source_authority, source_reference=charge.source_reference,
    )


def calculate_fee_and_tax(db: Session, gross_amount: Decimal, tax_fee_rules: TaxFeeRules,
                          *, instrument_type: str | None = None) -> FeeTaxCalculation:
    """gross - fee - tax_on_fee - commission - statutory charges = net.

    The fee and commission rates are commercial figures (PROTOTYPE_ASSUMPTION
    unless the client's config says otherwise, see docs/tax-rules.md); the
    tax-on-fee rate comes from a versioned, sourced TaxRule and is never
    hardcoded here. Each statutory charge carries its own provenance so a
    deduction can be attributed rather than merely subtracted.
    """
    tax_rule = get_tax_rule(db, tax_fee_rules.tax_on_fee.tax_rule_id)

    fee_rate = Decimal(str(tax_fee_rules.fee.rate_percent))
    fee_amount = round_decimal(gross_amount * fee_rate / _HUNDRED, 2, "HALF_UP")

    tax_rate = tax_rule.rate_percent
    tax_amount = round_decimal(fee_amount * tax_rate / _HUNDRED, 2, "HALF_UP")

    charge_lines: list[ChargeLine] = []

    commission = tax_fee_rules.commission
    if commission is not None and (commission.rate_percent or commission.minimum_amount):
        raw = round_decimal(gross_amount * Decimal(str(commission.rate_percent)) / _HUNDRED, 2, "HALF_UP")
        amount = max(raw, Decimal(str(commission.minimum_amount)))
        if commission.maximum_amount is not None:
            amount = min(amount, Decimal(str(commission.maximum_amount)))
        if amount > 0:
            charge_lines.append(ChargeLine(
                code="COMMISSION", label=commission.label, basis="GROSS",
                rate_percent=Decimal(str(commission.rate_percent)), amount=amount,
                verification_status=commission.verification_status,
            ))

    for charge in tax_fee_rules.statutory_charges:
        line = _statutory_charge_line(charge, gross=gross_amount, fee=fee_amount, tax=tax_amount,
                                      instrument_type=instrument_type)
        if line is not None:
            charge_lines.append(line)

    charges_total = sum((line.amount for line in charge_lines), Decimal(0))
    net_amount = gross_amount - fee_amount - tax_amount - charges_total

    return FeeTaxCalculation(
        gross_amount=gross_amount, fee_amount=fee_amount, fee_rate_percent=fee_rate,
        tax_amount=tax_amount, tax_rate_percent=tax_rate, net_amount=net_amount, tax_rule=tax_rule,
        charge_lines=charge_lines,
    )
