"""Scenarios that only make sense once accounts are the reconciliation unit.

A second bank format for the same client, a treasury sweep whose two legs land
in two different banks, a settlement credit tied to its bank line by UTR, and
a tax challan keyed on the CIN rather than the amount. Each exists to exercise
one of the reconciliation types in app.domains.reconciliation.types.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from app.synthetic.scenarios import Scenario, _fmt, _tag

ICICI_PARTIES = [
    "ZENITH ADVISORY LLP", "KAVERI TRADING CO", "NILGIRI EXPORTS", "SARASWAT VENTURES",
]


# ---------------------------------------------------------------------------
# Meridian: ICICI statement -- a second bank format for the same client
# ---------------------------------------------------------------------------

def _icici_row(*, txn_date: date, value_date: date, amount: Decimal, credit: bool,
               utr: str, remarks: str, cheque: str = "", batch_ref: str = "") -> dict:
    """ICICI names its columns differently, formats dates differently, and
    splits debit and credit under different headings than HDFC. Same meaning,
    and the canonical mapping is what makes that irrelevant downstream."""
    return {
        "Transaction Date": _fmt(txn_date, "%d-%m-%Y"),
        "Value Date": _fmt(value_date, "%d-%m-%Y"),
        "Withdrawal Amount (INR)": "" if credit else str(amount),
        "Deposit Amount (INR)": str(amount) if credit else "",
        "Transaction ID": utr,
        "Cheque Number": cheque,
        "Transaction Remarks": remarks,
        "Batch Reference": batch_ref,
    }


def mrdn_icici_exact_match(seq: int, base_date: date, rng: random.Random) -> Scenario:
    eco_id = f"MRDN-ICICI-EXACT-{seq:04d}"
    utr = f"UTR{880000 + seq}"
    amount = Decimal(rng.randrange(80000, 900000)) / 100
    party = rng.choice(ICICI_PARTIES)
    txn_date = base_date - timedelta(days=rng.randint(0, 3))

    return Scenario(
        scenario_name="EXACT_IDENTIFIER_MATCH",
        economic_transaction_id=eco_id,
        client_code="MRDN",
        rows_by_source={
            "internal_ledger": [_tag({
                "Trade_ID": utr,
                "Txn_Reference": "",
                "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
                "Amount": str(amount),
                "Dr_Cr_Indicator": "C",
                "Counterparty_Name": party,
                "Narration": f"NEFT collection from {party}",
                "Settlement_Batch_Ref": "",
            }, eco_id)],
            "icici_statement": [_tag(_icici_row(
                txn_date=txn_date, value_date=txn_date, amount=amount, credit=True,
                utr=utr, remarks=f"NEFT/{utr}/{party}",
            ), eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "icici_statement"]},
    )


def mrdn_icici_outstanding_cheque(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """A cheque issued and booked that the bank has not yet cleared. The
    classic Bank-to-GL timing difference: nothing is wrong, the item simply
    has not reached the statement yet."""
    eco_id = f"MRDN-ICICI-OUTSTANDING-{seq:04d}"
    amount = Decimal(rng.randrange(150000, 700000)) / 100
    party = rng.choice(["DECCAN INFRA PVT LTD", "KONKAN LOGISTICS"])
    issued = base_date - timedelta(days=1)

    return Scenario(
        scenario_name="MISSING_EXTERNAL_RECORD",
        economic_transaction_id=eco_id,
        client_code="MRDN",
        rows_by_source={
            "internal_ledger": [_tag({
                "Trade_ID": "",
                "Txn_Reference": f"CHQ{560000 + seq}",
                "Posting_Date": _fmt(issued, "%Y-%m-%d"),
                "Amount": str(-amount),
                "Dr_Cr_Indicator": "D",
                "Counterparty_Name": party,
                "Narration": f"CHQ {560000 + seq} issued to {party}, awaiting presentation",
                "Settlement_Batch_Ref": "",
            }, eco_id)],
        },
        expected_exception_type="MISSING_EXTERNAL_RECORD",
    )


def mrdn_internal_sweep(seq: int, base_date: date, rng: random.Random,
                        *, from_account: str, to_account: str) -> Scenario:
    """A treasury sweep between two of the client's own accounts.

    Four records for one movement: the treasury instruction's two legs, the
    debit on the source bank's statement, and the credit on the destination
    bank's. Every leg reconciles, and none of it changes total cash -- which
    is exactly why both legs are tagged INTERNAL_ACCOUNT.
    """
    eco_id = f"MRDN-SWEEP-{seq:04d}"
    instruction = f"SWP{430000 + seq}"
    amount = Decimal(rng.randrange(2_500_000, 12_000_000)) / 100
    sweep_date = base_date - timedelta(days=rng.randint(0, 2))
    narration = f"RTGS OWN ACCOUNT SWEEP {instruction} {from_account} to {to_account}"

    return Scenario(
        scenario_name="INTERNAL_TRANSFER",
        economic_transaction_id=eco_id,
        client_code="MRDN",
        rows_by_source={
            "treasury_ledger": [
                _tag({
                    "Instruction_Ref": f"{instruction}OUT",
                    "Leg_Date": _fmt(sweep_date, "%Y-%m-%d"),
                    "Leg_Amount": str(-amount),
                    "Leg_Direction": "OUT",
                    "Own_Account": from_account,
                    "Other_Account": to_account,
                    "Counterparty": "MERIDIAN BROKING OWN ACCOUNT",
                    "Party_Type": "INTERNAL_ACCOUNT",
                    "Method": "INTERNAL_TRANSFER",
                    "Narrative": narration,
                }, eco_id),
                _tag({
                    "Instruction_Ref": f"{instruction}IN",
                    "Leg_Date": _fmt(sweep_date, "%Y-%m-%d"),
                    "Leg_Amount": str(amount),
                    "Leg_Direction": "IN",
                    "Own_Account": to_account,
                    "Other_Account": from_account,
                    "Counterparty": "MERIDIAN BROKING OWN ACCOUNT",
                    "Party_Type": "INTERNAL_ACCOUNT",
                    "Method": "INTERNAL_TRANSFER",
                    "Narrative": narration,
                }, eco_id),
            ],
            "bank_statement": [_tag({
                "Txn Date": _fmt(sweep_date, "%d/%m/%Y"),
                "Value Date": _fmt(sweep_date, "%d/%m/%Y"),
                "Debit": str(amount),
                "Credit": "",
                "UTR Number": f"{instruction}OUT",
                "Chq/Ref No": "",
                "Description": narration,
                "Batch Ref": "",
            }, eco_id)],
            "icici_statement": [_tag(_icici_row(
                txn_date=sweep_date, value_date=sweep_date, amount=amount, credit=True,
                utr=f"{instruction}IN", remarks=narration,
            ), eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["treasury_ledger", "bank_statement", "icici_statement"]},
    )


# ---------------------------------------------------------------------------
# Sahyadri: settlement credits landing in the bank, and tax challans
# ---------------------------------------------------------------------------

def shyd_settlement_bank_credit(seq: int, base_date: date, rng: random.Random,
                                *, gross: Decimal, net: Decimal, settlement_ref: str) -> Scenario:
    """Settlement to Bank: the aggregator's net figure arriving as a single
    credit, tied to the settlement by its UTR rather than by amount. This is a
    different proof from Payments to Settlement, over the same money."""
    eco_id = f"SHYD-SETL-BANK-{seq:04d}"
    credited = base_date - timedelta(days=rng.randint(0, 1))

    return Scenario(
        scenario_name="EXACT_IDENTIFIER_MATCH",
        economic_transaction_id=eco_id,
        client_code="SHYD",
        rows_by_source={
            "internal_ledger": [_tag({
                "InternalRef": f"SETLEXP{seq:05d}",
                "OrderId": settlement_ref,
                "PostedOn": credited.isoformat(),
                "Amount": str(net),
                "DrCr": "CR",
                "CustomerName": "PAYMENT AGGREGATOR",
                "Notes": f"Expected settlement {settlement_ref}, gross {gross} net of charges",
                "SettlementBatchRef": "",
            }, eco_id)],
            "bank_statement": [_tag({
                "Tran Date": _fmt(credited, "%d/%m/%Y"),
                "Value Date": _fmt(credited, "%d/%m/%Y"),
                "Withdrawal Amt": "",
                "Deposit Amt": str(net),
                "Chq/Ref No": settlement_ref,
                "Narration": f"NEFT AGGREGATOR SETTLEMENT {settlement_ref}",
                "Settlement Ref": "",
            }, eco_id)],
        },
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "bank_statement"]},
    )


def shyd_tax_challan(seq: int, base_date: date, rng: random.Random, *, tax_type: str,
                     amount: Decimal, matched: bool = True) -> Scenario:
    """Tax liability to bank: the liability booked internally, the challan the
    portal issued, and the debit that discharged it. The challan number is the
    key -- a period's liability may be paid across several challans, so
    matching on amount alone would tie the wrong ones together."""
    eco_id = f"SHYD-TAX-{tax_type}-{seq:04d}"
    challan = f"CIN{base_date:%Y%m%d}{4400 + seq}"
    paid = base_date - timedelta(days=rng.randint(0, 2))

    rows: dict[str, list[dict]] = {
        "internal_ledger": [_tag({
            "InternalRef": f"TAXLIAB{seq:05d}",
            "OrderId": challan,
            "PostedOn": paid.isoformat(),
            "Amount": str(-amount),
            "DrCr": "DR",
            "CustomerName": f"{tax_type} AUTHORITY",
            "Notes": f"{tax_type} liability discharged, challan {challan}",
            "SettlementBatchRef": "",
        }, eco_id)],
    }
    if matched:
        rows["tax_challan"] = [_tag({
            "Challan Number": challan,
            "Payment Date": _fmt(paid, "%d/%m/%Y"),
            "Amount Paid": str(amount),
            "Tax Type": f"{tax_type} AUTHORITY",
            "Bank Reference": challan,
            "Remarks": f"{tax_type} paid for the period, challan {challan}",
        }, eco_id)]

    return Scenario(
        scenario_name="EXACT_IDENTIFIER_MATCH" if matched else "MISSING_EXTERNAL_RECORD",
        economic_transaction_id=eco_id,
        client_code="SHYD",
        rows_by_source=rows,
        expected_cardinality="ONE_TO_ONE" if matched else None,
        expected_exception_type=None if matched else "MISSING_EXTERNAL_RECORD",
    )
