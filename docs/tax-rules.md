# Tax Rules — What Is Verified, What Isn't

This document exists because spec principle #15/#39 requires the system to
never invent a tax rate and to clearly separate "implemented and verified"
from "prototype assumption" and "not implemented." It is the honesty ledger
for every `TaxRule` row seeded into the system.

## VERIFIED: `GST_ON_PAYMENT_GATEWAY_FEE_V1`

| Field | Value |
|---|---|
| Tax type | GST |
| Applies to | The payment-gateway processing/service fee (MDR-equivalent) charged by the gateway to the merchant — the fee line item only |
| Explicitly does NOT apply to | The settled principal amount, or any interest component |
| Rate | 18% (9% CGST + 9% SGST intra-state, or 18% IGST inter-state) |
| Classification | SAC 9971 — "Financial and related services" |
| Source | CBIC Notification No. 11/2017-Central Tax (Rate), dated 28-06-2017 |
| Effective from | 2017-07-01 |
| Jurisdiction | India |

**Verification basis.** The notification number, date, heading (9971), and
18% rate were corroborated by cross-referencing the CBIC/GST Council
notification index (`gstcouncil.gov.in`, `cbic-gst.gov.in`) against multiple
independent professional GST-compliance references that all cite the same
notification, date, and rate for this heading. The primary notification PDF
itself could not be machine-fetched during this build (the fetch tool hit a
connection error against both the CBIC and GST Council PDF hosts) — this rule
is therefore **corroborated via secondary sources that agree with each other
and cite the same primary instrument**, not a direct quote verified against
the primary PDF's text. That distinction is recorded here rather than
overstated as a primary-source confirmation.

**Explicit scope limit.** A separate CBIC clarification exempts RBI-regulated
Payment Aggregators' fund-settlement function for small-value card
transactions from GST in certain circumstances. That exemption is **out of
scope** for this system and must never be applied here: the synthetic/demo
scenario this rule is used against models a standard payment-gateway
processing fee, not a regulated aggregator's fund pass-through function. If
this system is ever pointed at real aggregator data, this rule must be
re-reviewed against that exemption before being applied.

**Where it's used.** `app/domains/reconciliation/passes/pass5_fee_tax_explained.py`
computes `net_expected = gross − fee − (fee × 18%)` for the one client
scenario configured to use it (Client B's payment-gateway settlement, via
`tax_fee_rules.tax_on_fee.tax_rule_id` in `configs/clients/client_b/v1.yaml`),
and only classifies a discrepancy as `EXPLAINED_BY_FEE_TAX` if the observed
net matches within the configured rounding tolerance — full evidence
(rule id, version, rate, source) is attached to the resulting match.

## PROTOTYPE ASSUMPTION (not a tax rule, but adjacent): payment-gateway MDR fee rate

The 2% fee rate used in the demo (`tax_fee_rules.fee.rate_percent` in Client
B's config) is a **commercial rate**, not a regulatory or statutory figure —
Merchant Discount Rates are individually negotiated between a merchant and
its payment aggregator/bank and are not published by a government authority.
It is marked `PROTOTYPE_ASSUMPTION` in config, not `VERIFIED`, and a real
deployment must source it from the client's actual merchant agreement.

## NOT VERIFIED: `GST_ON_BROKERAGE_V1`

Seeded so Meridian (MRDN) can reference a GST-on-brokerage rate, and seeded
with `verification_status = NOT_VERIFIED` on purpose.

The 18% figure is asserted on the same Heading 9971 ("Financial and related
services") basis as the payment-gateway rule above, but **brokerage-specific
applicability was not independently verified against a primary source during
this build**. It is deliberately not marked VERIFIED: an unverified rate
sitting next to a verified one must not borrow its credibility. The Tax &
Fees window renders `verification_status` for every rate, so an operator sees
this distinction on screen rather than having to read this file.

## PROTOTYPE ASSUMPTIONS: statutory charge rates in client configs

`tax_fee_rules.statutory_charges` in both client configs carries illustrative
rates — STT, SEBI turnover fee, exchange transaction charges and stamp duty
for MRDN; TDS under section 194-O for SHYD. **None of these rates was
verified during this build**, and several genuinely vary by segment, by
buy/sell leg, or by threshold conditions the prototype does not model. Each
entry carries `verification_status: NOT_VERIFIED` and a note saying so, and
each is editable in the Tax & Fees window — that is where a real deployment
supplies the client's actual figures.

They are computed and deducted for real (see
`app/domains/tax/service.calculate_fee_and_tax`), so changing a rate changes
which settlements reconcile. That is intentional: a rate the system displays
but does not apply would be worse than no rate at all.

## NOT VERIFIED / NOT IMPLEMENTED

Everything else in Indian tax/payment-charge territory is explicitly **not**
implemented in this prototype, including but not limited to: TCS, GST on any
instrument/transaction type other than those scoped above, threshold and
exemption logic for any levy, and bank-charge-specific tax treatment. No rate
or threshold for any of these is guessed or hardcoded anywhere in the
codebase. If the system is asked (via the AI Controller or otherwise) about
tax treatment outside the rules above, it must say the treatment is not
implemented/not verified rather than fabricate an answer.
