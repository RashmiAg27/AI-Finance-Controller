"""Seed data for TaxRule. Every rule here must have a corresponding entry in
docs/tax-rules.md explaining exactly what was verified and how -- this module
must never grow a rule that document doesn't also justify."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tax import TaxRule

GST_ON_PAYMENT_GATEWAY_FEE_V1 = dict(
    rule_id="GST_ON_PAYMENT_GATEWAY_FEE_V1",
    rule_version=1,
    client_scope=None,  # global -- any client whose config references this rule_id
    instrument_type="PAYMENT_GATEWAY_SETTLEMENT",
    tax_type="GST",
    calculation_basis="fee_amount",
    rate_percent="18.000",
    effective_from=date(2017, 7, 1),
    effective_to=None,
    jurisdiction="IN",
    applicability=(
        "Applies only to the payment-gateway processing/service fee (MDR-equivalent) line item "
        "charged by the gateway to the merchant -- SAC 9971 'Financial and related services'. "
        "Does NOT apply to the settled principal amount or to any interest component. Does NOT "
        "apply to RBI-regulated Payment Aggregators' fund-settlement function for small-value "
        "card transactions (a separate CBIC exemption, out of scope here)."
    ),
    source_authority="CBIC (Central Board of Indirect Taxes and Customs)",
    source_reference="Notification No. 11/2017-Central Tax (Rate), dated 28-06-2017, Heading 9971",
    source_url="https://cbic-gst.gov.in/central-tax-rate-notfns.html",
    verification_status="VERIFIED",
    verification_note=(
        "Notification number/date/heading/rate corroborated across the CBIC/GST Council notification "
        "index and multiple independent professional GST-compliance references that agree on the same "
        "primary instrument. The primary notification PDF text itself could not be machine-fetched "
        "during this build (connection error) -- see docs/tax-rules.md for the full verification basis."
    ),
)


GST_ON_BROKERAGE_V1 = dict(
    rule_id="GST_ON_BROKERAGE_V1",
    rule_version=1,
    client_scope=None,
    instrument_type="EXCH_OBLIGATION",
    tax_type="GST",
    calculation_basis="fee_amount",
    rate_percent="18.000",
    effective_from=date(2017, 7, 1),
    effective_to=None,
    jurisdiction="IN",
    applicability=(
        "Applies only to the brokerage/commission line item charged by a stockbroker to its client. "
        "Does NOT apply to the settled principal amount, to Securities Transaction Tax, to stamp duty, "
        "or to any statutory levy -- those are separate charges, not services attracting GST at this "
        "rate."
    ),
    source_authority="CBIC (Central Board of Indirect Taxes and Customs)",
    source_reference="Heading 9971, 'Financial and related services' (rate schedule under GST)",
    source_url="https://cbic-gst.gov.in/central-tax-rate-notfns.html",
    verification_status="NOT_VERIFIED",
    verification_note=(
        "The 18% figure is asserted here on the same Heading 9971 basis as the payment-gateway fee rule, "
        "but brokerage-specific applicability was NOT independently verified against a primary source "
        "during this build. It is seeded as NOT_VERIFIED deliberately: the system must show an unverified "
        "rate as unverified rather than borrow the credibility of the rule next to it. See "
        "docs/tax-rules.md."
    ),
)


def ensure_seed_rules(db: Session) -> None:
    for rule_data in (GST_ON_PAYMENT_GATEWAY_FEE_V1, GST_ON_BROKERAGE_V1):
        existing = db.execute(select(TaxRule).where(TaxRule.rule_id == rule_data["rule_id"])).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(TaxRule(**rule_data))
    db.flush()
