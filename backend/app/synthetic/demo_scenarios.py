"""Fabricated source rows for the demo world's two clients.

The bank-statement and payment-gateway cycles reuse the existing, tested
scenario builders in app.synthetic.scenarios (retagged onto the demo client
codes). This module adds the two feeds those builders don't cover -- an
exchange clearing obligation file for Meridian and a NACH mandate return
file for Sahyadri -- shaped like the real thing: UMRNs, IFSC codes, clearing
member codes, settlement numbers, NPCI return reasons.

Nothing here leaks the answer into a matchable field. As in scenarios.py the
only place the expected outcome is recorded is the hidden
`_ground_truth_economic_id` column, which no client config maps.
"""
from __future__ import annotations

import random
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from app.synthetic.scenarios import Scenario, _fmt, _tag

CLEARING_MEMBERS = [
    "KOTAK SECURITIES CLEARING",
    "ICICI SEC PRIMARY DEALERSHIP",
    "AXIS CAPITAL CLEARING",
    "HDFC SECURITIES CLEARING",
]
BORROWERS = [
    "R KUMAR TRADERS", "S PATEL ENTERPRISES", "A SHARMA & SONS",
    "N REDDY AGENCIES", "V IYER PROVISION STORES", "M DESHMUKH KIRANA",
]
SPONSOR_IFSC = ["HDFC0000123", "ICIC0004567", "SBIN0011223", "UTIB0000456"]
NACH_RETURN_REASONS = [
    "Insufficient funds",
    "Account closed",
    "Mandate not registered",
    "Payment stopped by drawer",
]


def retag(scenarios: list[Scenario], client_code: str) -> list[Scenario]:
    """Reuses a tested scenario set under a different client code. The rows
    themselves are unchanged -- the demo clients' configs declare the same
    column names as the fixture clients they were written for."""
    return [replace(s, client_code=client_code) for s in scenarios]


# ---------------------------------------------------------------------------
# Meridian: internal_ledger (XLSX) <-> exchange_obligation (CSV)
# ---------------------------------------------------------------------------

def _obligation_row(*, trade_id: str, settlement_no: str, trade_date: date, settlement_date: date,
                    amount: Decimal, member: str, remarks: str, batch_ref: str = "") -> dict:
    return {
        "Settlement No": settlement_no,
        "Trade ID": trade_id,
        "Trade Date": _fmt(trade_date, "%d-%b-%Y"),
        "Settlement Date": _fmt(settlement_date, "%d-%b-%Y"),
        "Net Obligation": str(amount),
        "Clearing Member": member,
        "Remarks": remarks,
        "Obligation Batch Ref": batch_ref,
    }


def _payout_row(*, trade_id: str, posting_date: date, amount: Decimal, member: str,
                narration: str, txn_reference: str = "", batch_ref: str = "") -> dict:
    return {
        "Trade_ID": trade_id,
        "Txn_Reference": txn_reference,
        "Posting_Date": _fmt(posting_date, "%Y-%m-%d"),
        "Amount": str(amount),
        "Dr_Cr_Indicator": "C",
        "Counterparty_Name": member,
        "Narration": narration,
        "Settlement_Batch_Ref": batch_ref,
    }


def mrdn_obligation_exact_match(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """The ordinary case: the clearing corporation echoes the member's own
    trade id, so Pass 1 links the two sides on reference alone."""
    eco_id = f"MRDN-OBL-EXACT-{seq:04d}"
    trade_id = f"TRD{700000 + seq}"
    amount = Decimal(rng.randrange(2_000_00, 40_000_00)) / 100
    member = rng.choice(CLEARING_MEMBERS)
    trade_date = base_date - timedelta(days=rng.randint(1, 4))
    settlement_date = trade_date + timedelta(days=1)

    return Scenario(
        scenario_name="EXACT_IDENTIFIER_MATCH",
        economic_transaction_id=eco_id,
        client_code="MRDN",
        rows_by_source={
            "internal_ledger": [_tag(_payout_row(
                trade_id=trade_id, posting_date=settlement_date, amount=amount, member=member,
                narration=f"Exchange settlement obligation payout, CM segment, settlement {trade_id}",
            ), eco_id)],
            "exchange_obligation": [_tag(_obligation_row(
                trade_id=trade_id, settlement_no=f"NSE/CM/{settlement_date:%Y%m%d}/{seq:04d}",
                trade_date=trade_date, settlement_date=settlement_date, amount=amount, member=member,
                remarks="Net funds obligation, cash segment",
            ), eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "exchange_obligation"]},
    )


def mrdn_obligation_charges_explained(seq: int, base_date: date, rng: random.Random,
                                      gross: Decimal, net: Decimal) -> Scenario:
    """The OMS books the payout gross; the clearing corporation credits it net
    of brokerage, GST on brokerage, clearing commission and statutory levies.
    Neither side carries a shared trade reference on these lines, so the only
    thing that can connect them is the fee/charge arithmetic in Pass 5.

    `net` is computed by the caller using the client's OWN configured rates
    through app.domains.tax.service, never by restating the arithmetic here --
    if a rate is edited in the Tax & Fees window, this data stays consistent
    with it.
    """
    eco_id = f"MRDN-OBL-CHARGES-{seq:04d}"
    member = rng.choice(CLEARING_MEMBERS)
    trade_date = base_date - timedelta(days=rng.randint(1, 3))
    settlement_date = trade_date + timedelta(days=1)

    return Scenario(
        scenario_name="FEE_ADJUSTED_SETTLEMENT",
        economic_transaction_id=eco_id,
        client_code="MRDN",
        rows_by_source={
            "internal_ledger": [_tag(_payout_row(
                trade_id="", posting_date=settlement_date, amount=gross, member=member,
                narration="Gross exchange obligation booked, brokerage and statutory charges "
                          "to be deducted on settlement",
            ), eco_id)],
            "exchange_obligation": [_tag(_obligation_row(
                trade_id="", settlement_no=f"NSE/CM/{settlement_date:%Y%m%d}/{9000 + seq}",
                trade_date=trade_date, settlement_date=settlement_date, amount=net, member=member,
                remarks="Net payout after brokerage, GST, STT, stamp duty and exchange charges",
            ), eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "exchange_obligation"]},
    )


def mrdn_obligation_missing_internal(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """An obligation the exchange reports that the OMS never booked."""
    eco_id = f"MRDN-OBL-MISSINT-{seq:04d}"
    trade_id = f"TRD{760000 + seq}"
    amount = Decimal(rng.randrange(5_000_00, 60_000_00)) / 100
    member = rng.choice(CLEARING_MEMBERS)
    trade_date = base_date - timedelta(days=2)

    return Scenario(
        scenario_name="MISSING_INTERNAL_RECORD",
        economic_transaction_id=eco_id,
        client_code="MRDN",
        rows_by_source={
            "exchange_obligation": [_tag(_obligation_row(
                trade_id=trade_id, settlement_no=f"NSE/CM/{trade_date:%Y%m%d}/{8000 + seq}",
                trade_date=trade_date, settlement_date=trade_date + timedelta(days=1),
                amount=amount, member=member, remarks="Net funds obligation, cash segment",
            ), eco_id)],
        },
        expected_exception_type="MISSING_INTERNAL_RECORD",
    )


def mrdn_obligation_unexplained_variance(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """Reference-matched, but the amounts differ by a sum no configured
    brokerage or statutory charge accounts for -- exactly the case that must
    surface as a FEE_VARIANCE exception rather than be absorbed silently."""
    eco_id = f"MRDN-OBL-VARIANCE-{seq:04d}"
    trade_id = f"TRD{780000 + seq}"
    gross = Decimal(rng.randrange(10_000_00, 30_000_00)) / 100
    observed = gross - Decimal("1847.50")  # not derivable from any configured rate
    member = rng.choice(CLEARING_MEMBERS)
    trade_date = base_date - timedelta(days=2)
    settlement_date = trade_date + timedelta(days=1)

    return Scenario(
        scenario_name="REFERENCE_MATCHED_UNEXPLAINED_VARIANCE",
        economic_transaction_id=eco_id,
        client_code="MRDN",
        rows_by_source={
            "internal_ledger": [_tag(_payout_row(
                trade_id=trade_id, posting_date=settlement_date, amount=gross, member=member,
                narration=f"Exchange settlement obligation payout, settlement {trade_id}",
            ), eco_id)],
            "exchange_obligation": [_tag(_obligation_row(
                trade_id=trade_id, settlement_no=f"NSE/CM/{settlement_date:%Y%m%d}/{7000 + seq}",
                trade_date=trade_date, settlement_date=settlement_date, amount=observed, member=member,
                remarks="Net funds obligation, cash segment -- adjustment applied",
            ), eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "exchange_obligation"]},
    )


# ---------------------------------------------------------------------------
# Sahyadri: internal_ledger (CSV) <-> nach_return (CSV)
# ---------------------------------------------------------------------------

def _nach_row(*, umrn: str, txn_ref: str, presentation_date: date, settlement_date: date,
              amount: Decimal, holder: str, status: str, reason: str) -> dict:
    return {
        "UMRN": umrn,
        "Transaction Ref No": txn_ref,
        "Presentation Date": _fmt(presentation_date, "%d/%m/%Y"),
        "Settlement Date": _fmt(settlement_date, "%d/%m/%Y"),
        "Amount": str(amount),
        "Debit Account Holder": holder,
        "Status": status,
        "Return Reason": reason,
    }


def _collection_row(*, internal_ref: str, order_id: str, posted_on: date, amount: Decimal,
                    customer: str, notes: str, batch_ref: str = "") -> dict:
    return {
        "InternalRef": internal_ref,
        "OrderId": order_id,
        "PostedOn": _fmt(posted_on, "%Y-%m-%d"),
        "Amount": str(amount),
        "DrCr": "CR",
        "CustomerName": customer,
        "Notes": notes,
        "SettlementBatchRef": batch_ref,
    }


def _umrn(seq: int, rng: random.Random) -> str:
    return f"{rng.choice(SPONSOR_IFSC)}{6000000000 + seq}"


def shyd_nach_successful_collection(seq: int, base_date: date, rng: random.Random) -> Scenario:
    eco_id = f"SHYD-NACH-OK-{seq:04d}"
    order_id = f"COLL{500000 + seq}"
    amount = Decimal(rng.randrange(250000, 1800000)) / 100
    customer = rng.choice(BORROWERS)
    presented = base_date - timedelta(days=rng.randint(1, 3))

    return Scenario(
        scenario_name="EXACT_IDENTIFIER_MATCH",
        economic_transaction_id=eco_id,
        client_code="SHYD",
        rows_by_source={
            "internal_ledger": [_tag(_collection_row(
                internal_ref=f"EMI{seq:06d}", order_id=order_id, posted_on=presented, amount=amount,
                customer=customer, notes=f"EMI collection presented via NACH, instruction {order_id}",
            ), eco_id)],
            "nach_return": [_tag(_nach_row(
                umrn=_umrn(seq, rng), txn_ref=order_id, presentation_date=presented,
                settlement_date=presented + timedelta(days=1), amount=amount, holder=customer,
                status="SUCCESS", reason="",
            ), eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "nach_return"]},
    )


def shyd_nach_returned_mandate(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """The sponsor bank returned the presentation, but the collections ledger
    still shows the EMI as collected. The reference ties them together and the
    amounts agree, so this is not an amount break -- what makes it an
    operational problem is the returned status, which the reconciliation
    surfaces by linking the two records for review."""
    eco_id = f"SHYD-NACH-RETURN-{seq:04d}"
    order_id = f"COLL{540000 + seq}"
    amount = Decimal(rng.randrange(300000, 1500000)) / 100
    customer = rng.choice(BORROWERS)
    presented = base_date - timedelta(days=2)

    return Scenario(
        scenario_name="EXACT_IDENTIFIER_MATCH",
        economic_transaction_id=eco_id,
        client_code="SHYD",
        rows_by_source={
            "internal_ledger": [_tag(_collection_row(
                internal_ref=f"EMI{500 + seq:06d}", order_id=order_id, posted_on=presented, amount=amount,
                customer=customer, notes=f"EMI collection presented via NACH, instruction {order_id}",
            ), eco_id)],
            "nach_return": [_tag(_nach_row(
                umrn=_umrn(900 + seq, rng), txn_ref=order_id, presentation_date=presented,
                settlement_date=presented + timedelta(days=1), amount=amount, holder=customer,
                status="RETURNED", reason=rng.choice(NACH_RETURN_REASONS),
            ), eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "nach_return"]},
    )


def shyd_nach_amount_break(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """Same instruction reference, different amount -- a partial collection
    the ledger booked in full. Pass 1 links them on reference without ever
    looking at amount, so the gap only surfaces in settlement, as a variance
    no configured fee or charge explains."""
    eco_id = f"SHYD-NACH-BREAK-{seq:04d}"
    order_id = f"COLL{580000 + seq}"
    booked = Decimal(rng.randrange(600000, 1600000)) / 100
    collected = (booked / 2).quantize(Decimal("0.01"))
    customer = rng.choice(BORROWERS)
    presented = base_date - timedelta(days=1)

    return Scenario(
        scenario_name="REFERENCE_MATCHED_UNEXPLAINED_VARIANCE",
        economic_transaction_id=eco_id,
        client_code="SHYD",
        rows_by_source={
            "internal_ledger": [_tag(_collection_row(
                internal_ref=f"EMI{800 + seq:06d}", order_id=order_id, posted_on=presented, amount=booked,
                customer=customer, notes=f"Full EMI booked against instruction {order_id}",
            ), eco_id)],
            "nach_return": [_tag(_nach_row(
                umrn=_umrn(1800 + seq, rng), txn_ref=order_id, presentation_date=presented,
                settlement_date=presented + timedelta(days=1), amount=collected, holder=customer,
                status="PARTIAL", reason="Part payment realised",
            ), eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "nach_return"]},
    )


def shyd_nach_missing_internal(seq: int, base_date: date, rng: random.Random) -> Scenario:
    eco_id = f"SHYD-NACH-MISSINT-{seq:04d}"
    amount = Decimal(rng.randrange(200000, 900000)) / 100
    customer = rng.choice(BORROWERS)
    presented = base_date - timedelta(days=2)

    return Scenario(
        scenario_name="MISSING_INTERNAL_RECORD",
        economic_transaction_id=eco_id,
        client_code="SHYD",
        rows_by_source={
            "nach_return": [_tag(_nach_row(
                umrn=_umrn(2600 + seq, rng), txn_ref=f"COLL{599000 + seq}", presentation_date=presented,
                settlement_date=presented + timedelta(days=1), amount=amount, holder=customer,
                status="SUCCESS", reason="",
            ), eco_id)],
        },
        expected_exception_type="MISSING_INTERNAL_RECORD",
    )


def shyd_nach_missing_external(seq: int, base_date: date, rng: random.Random) -> Scenario:
    eco_id = f"SHYD-NACH-MISSEXT-{seq:04d}"
    order_id = f"COLL{610000 + seq}"
    amount = Decimal(rng.randrange(200000, 900000)) / 100
    customer = rng.choice(BORROWERS)
    presented = base_date - timedelta(days=1)

    return Scenario(
        scenario_name="MISSING_EXTERNAL_RECORD",
        economic_transaction_id=eco_id,
        client_code="SHYD",
        rows_by_source={
            "internal_ledger": [_tag(_collection_row(
                internal_ref=f"EMI{1200 + seq:06d}", order_id=order_id, posted_on=presented, amount=amount,
                customer=customer, notes=f"EMI collection presented via NACH, instruction {order_id}",
            ), eco_id)],
        },
        expected_exception_type="MISSING_EXTERNAL_RECORD",
    )
