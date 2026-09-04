"""Named synthetic scenario builders with known ground truth.

Each scenario produces raw rows shaped exactly like a client's real source
columns (per its YAML config) plus an expected outcome. Rows never leak the
answer into any matchable field -- the only place the "correct" answer is
recorded is `economic_transaction_id`, carried in the hidden
`_ground_truth_economic_id` raw column that app.domains.normalization.service
copies straight into Transaction.metadata_json (and nowhere else). No client
config ever declares a field_mapping for that column, so it is structurally
invisible to every matching/tax/ML pass -- it exists only for the evaluation
harness and tests (see app.models.ground_truth).

New scenarios are added here milestone by milestone (M4 adds aggregation,
M5a adds genuinely ambiguous/unresolved cases) rather than generating
everything at once -- ground truth accumulates from M0 onward per the
approved plan, it is not a separate late phase.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
import random


@dataclass
class Scenario:
    scenario_name: str
    economic_transaction_id: str
    client_code: str
    rows_by_source: dict[str, list[dict]]  # source_id -> raw rows for that source
    expected_exception_type: str | None = None
    expected_cardinality: str | None = None
    expected_match_group: dict = field(default_factory=dict)


def _fmt(d: date, pattern: str) -> str:
    return d.strftime(pattern)


def _tag(row: dict, eco_id: str) -> dict:
    return {**row, "_ground_truth_economic_id": eco_id}


# ---------------------------------------------------------------------------
# Client A: internal_ledger (XLSX) <-> bank_statement (CSV)
# ---------------------------------------------------------------------------

def client_a_exact_match(seq: int, base_date: date, rng: random.Random) -> Scenario:
    eco_id = f"CA-EXACT-{seq:04d}"
    utr = f"UTR{100000 + seq}"
    amount = Decimal(rng.randrange(5000, 500000)) / 100
    counterparty = rng.choice(["ACME TRADERS", "SUNRISE LOGISTICS", "BLUE OCEAN EXPORTS", "NORTHSTAR AGRO"])
    txn_date = base_date + timedelta(days=rng.randint(0, 20))

    internal_row = _tag({
        "Trade_ID": utr,  # linked via identifier_linkage: UTR -> TRADE_ID, DIRECT_EQUIVALENT
        "Txn_Reference": f"TXNREF{seq:05d}",
        "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(amount),
        "Dr_Cr_Indicator": "D",
        "Counterparty_Name": counterparty,
        "Narration": f"NEFT PAYMENT TO {counterparty}",
    }, eco_id)
    bank_row = _tag({
        "Txn Date": _fmt(txn_date, "%d/%m/%Y"),
        "Value Date": _fmt(txn_date, "%d/%m/%Y"),
        "Debit": str(amount),
        "Credit": "",
        "UTR Number": utr,
        "Chq/Ref No": "",
        "Description": f"NEFT-{counterparty}",
    }, eco_id)
    return Scenario(
        scenario_name="EXACT_IDENTIFIER_MATCH",
        economic_transaction_id=eco_id,
        client_code="client_a",
        rows_by_source={"internal_ledger": [internal_row], "bank_statement": [bank_row]},
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "bank_statement"]},
    )


def client_a_normalized_reference_match(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """Cheque payment: ERP's Txn_Reference and the bank's Chq/Ref No carry the
    same cheque number but with different padding -- exercises Pass 2
    (normalized/partial reference), not Pass 1 (exact)."""
    eco_id = f"CA-NORMREF-{seq:04d}"
    cheque_no = f"{300000 + seq}"
    amount = Decimal(rng.randrange(10000, 200000)) / 100
    counterparty = rng.choice(["GREEN VALLEY FARMS", "APEX ENGINEERING", "SILVERLINE TEXTILES"])
    txn_date = base_date + timedelta(days=rng.randint(0, 20))

    internal_row = _tag({
        "Trade_ID": "",
        "Txn_Reference": f"CHQ0{cheque_no}",  # extra leading zero vs the bank's number
        "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(amount),
        "Dr_Cr_Indicator": "D",
        "Counterparty_Name": counterparty,
        "Narration": f"CHQ PAYMENT TO {counterparty}",
    }, eco_id)
    bank_row = _tag({
        "Txn Date": _fmt(txn_date, "%d/%m/%Y"),
        "Value Date": _fmt(txn_date + timedelta(days=1), "%d/%m/%Y"),
        "Debit": str(amount),
        "Credit": "",
        "UTR Number": "",
        "Chq/Ref No": f"CHQ{cheque_no}",
        "Description": f"CHQ CLEARED {counterparty}",
    }, eco_id)
    return Scenario(
        scenario_name="NORMALIZED_REFERENCE_MATCH",
        economic_transaction_id=eco_id,
        client_code="client_a",
        rows_by_source={"internal_ledger": [internal_row], "bank_statement": [bank_row]},
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "bank_statement"]},
    )


def client_a_timing_difference(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """No shared identifier at all (simulates a source that dropped the
    reference) -- only resolvable via Pass 3 (amount exact, value_date within
    the configured 2-day tolerance)."""
    eco_id = f"CA-TIMING-{seq:04d}"
    amount = Decimal(rng.randrange(20000, 300000)) / 100
    counterparty = rng.choice(["RIVERSIDE PACKAGING", "METRO FREIGHT", "CRESCENT STEEL"])
    txn_date = base_date + timedelta(days=rng.randint(0, 15))

    internal_row = _tag({
        "Trade_ID": "",
        "Txn_Reference": "",
        "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(amount),
        "Dr_Cr_Indicator": "D",
        "Counterparty_Name": counterparty,
        "Narration": f"NEFT PAYMENT TO {counterparty}",
    }, eco_id)
    bank_row = _tag({
        "Txn Date": _fmt(txn_date, "%d/%m/%Y"),
        "Value Date": _fmt(txn_date + timedelta(days=2), "%d/%m/%Y"),  # at the edge of the 2-day tolerance
        "Debit": str(amount),
        "Credit": "",
        "UTR Number": "",
        "Chq/Ref No": "",
        "Description": f"NEFT-{counterparty}",
    }, eco_id)
    return Scenario(
        scenario_name="TIMING_DIFFERENCE",
        economic_transaction_id=eco_id,
        client_code="client_a",
        rows_by_source={"internal_ledger": [internal_row], "bank_statement": [bank_row]},
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "bank_statement"]},
    )


def client_a_counterparty_variation(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """No shared identifier, amount off by a few paise (within Pass 4's
    tolerance of 1.00, but outside Pass 3's exact-amount requirement), and
    the counterparty name spelled slightly differently on each side --
    exercises Pass 4's fuzzy counterparty comparison."""
    eco_id = f"CA-CPTYVAR-{seq:04d}"
    base_amount = Decimal(rng.randrange(30000, 250000)) / 100
    txn_date = base_date + timedelta(days=rng.randint(0, 15))

    internal_row = _tag({
        "Trade_ID": "",
        "Txn_Reference": "",
        "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(base_amount),
        "Dr_Cr_Indicator": "D",
        "Counterparty_Name": "ACME TRADERS PVT LTD",
        "Narration": "NEFT PAYMENT TO ACME TRADERS PVT LTD",
    }, eco_id)
    bank_row = _tag({
        "Txn Date": _fmt(txn_date + timedelta(days=1), "%d/%m/%Y"),
        "Value Date": _fmt(txn_date + timedelta(days=1), "%d/%m/%Y"),
        "Debit": str(base_amount + Decimal("0.50")),  # within the 1.00 tolerance, but not exact
        "Credit": "",
        "UTR Number": "",
        "Chq/Ref No": "",
        # No clean counterparty column on the bank side at all -- the name is
        # only present embedded in free-text narration alongside other words,
        # which is why Pass 4 must fuzzy-match against description, not
        # require an exact counterparty field on both sides.
        "Description": "NEFT ACME TRADERS PVT LTD",
    }, eco_id)
    return Scenario(
        scenario_name="COUNTERPARTY_VARIATION",
        economic_transaction_id=eco_id,
        client_code="client_a",
        rows_by_source={"internal_ledger": [internal_row], "bank_statement": [bank_row]},
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "bank_statement"]},
    )


def client_a_split_settlement_one_to_many(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """One internal payment instruction settled by the bank as two separate
    credits (e.g. a value-dated split) -- no shared UTR/Trade_ID/cheque
    reference at all, and neither bank credit individually matches the full
    internal amount, so only Pass 6 (aggregation via SETTLEMENT_BATCH_REF)
    can resolve this: 1 internal : 2 external."""
    eco_id = f"CA-SPLIT-{seq:04d}"
    batch_ref = f"BATCHA{700000 + seq}"
    total = Decimal(rng.randrange(100000, 400000)) / 100
    part1 = (total / 2).quantize(Decimal("0.01"))
    part2 = total - part1
    counterparty = rng.choice(["HARBOUR LOGISTICS", "VERTEX MANUFACTURING"])
    txn_date = base_date + timedelta(days=rng.randint(0, 15))

    internal_row = _tag({
        "Trade_ID": "", "Txn_Reference": "",
        "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(total),
        "Dr_Cr_Indicator": "D",
        "Counterparty_Name": counterparty,
        "Narration": f"NEFT PAYMENT TO {counterparty} (split settlement)",
        "Settlement_Batch_Ref": batch_ref,
    }, eco_id)
    bank_row_1 = _tag({
        "Txn Date": _fmt(txn_date, "%d/%m/%Y"), "Value Date": _fmt(txn_date, "%d/%m/%Y"),
        "Debit": str(part1), "Credit": "", "UTR Number": "", "Chq/Ref No": "",
        "Description": f"NEFT-{counterparty}-PART1", "Batch Ref": batch_ref,
    }, eco_id)
    bank_row_2 = _tag({
        "Txn Date": _fmt(txn_date, "%d/%m/%Y"), "Value Date": _fmt(txn_date, "%d/%m/%Y"),
        "Debit": str(part2), "Credit": "", "UTR Number": "", "Chq/Ref No": "",
        "Description": f"NEFT-{counterparty}-PART2", "Batch Ref": batch_ref,
    }, eco_id)
    return Scenario(
        scenario_name="SPLIT_SETTLEMENT_ONE_TO_MANY",
        economic_transaction_id=eco_id,
        client_code="client_a",
        rows_by_source={"internal_ledger": [internal_row], "bank_statement": [bank_row_1, bank_row_2]},
        expected_cardinality="ONE_TO_MANY",
        expected_match_group={"sources": ["internal_ledger", "bank_statement"]},
    )


def client_a_missing_external_record(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """An internal payment with no bank-side counterpart at all -- e.g. it
    was recorded internally but never actually transmitted."""
    eco_id = f"CA-MISSEXT-{seq:04d}"
    amount = Decimal(rng.randrange(10000, 90000)) / 100
    txn_date = base_date + timedelta(days=rng.randint(0, 10))
    internal_row = _tag({
        "Trade_ID": "", "Txn_Reference": "",
        "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(amount), "Dr_Cr_Indicator": "D",
        "Counterparty_Name": "GHOST VENDOR LLP",
        "Narration": "NEFT PAYMENT TO GHOST VENDOR LLP",
    }, eco_id)
    return Scenario(
        scenario_name="MISSING_EXTERNAL_RECORD", economic_transaction_id=eco_id, client_code="client_a",
        rows_by_source={"internal_ledger": [internal_row]},
        expected_exception_type="MISSING_EXTERNAL_RECORD",
    )


def client_a_missing_internal_record(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """A bank credit with no internal-ledger counterpart -- e.g. an inbound
    payment the business hasn't booked yet."""
    eco_id = f"CA-MISSINT-{seq:04d}"
    amount = Decimal(rng.randrange(10000, 90000)) / 100
    txn_date = base_date + timedelta(days=rng.randint(0, 10))
    bank_row = _tag({
        "Txn Date": _fmt(txn_date, "%d/%m/%Y"), "Value Date": _fmt(txn_date, "%d/%m/%Y"),
        "Debit": "", "Credit": str(amount), "UTR Number": "", "Chq/Ref No": "",
        "Description": "NEFT-UNKNOWN INBOUND REMITTANCE",
    }, eco_id)
    return Scenario(
        scenario_name="MISSING_INTERNAL_RECORD", economic_transaction_id=eco_id, client_code="client_a",
        rows_by_source={"bank_statement": [bank_row]},
        expected_exception_type="MISSING_INTERNAL_RECORD",
    )


def client_a_duplicate_posting(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """The same internal payment posted twice by mistake, with no bank
    counterpart present -- both copies should end up as DUPLICATE exceptions
    referencing each other."""
    eco_id = f"CA-DUPE-{seq:04d}"
    trade_id = f"UTRDUPE{seq:04d}"
    amount = Decimal(rng.randrange(10000, 90000)) / 100
    txn_date = base_date + timedelta(days=rng.randint(0, 10))
    row = {
        "Trade_ID": trade_id, "Txn_Reference": "",
        "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(amount), "Dr_Cr_Indicator": "D",
        "Counterparty_Name": "DUPLICATE CORP",
        "Narration": "NEFT PAYMENT TO DUPLICATE CORP",
    }
    return Scenario(
        scenario_name="DUPLICATE", economic_transaction_id=eco_id, client_code="client_a",
        rows_by_source={"internal_ledger": [_tag(row, eco_id), _tag(dict(row), eco_id)]},
        expected_exception_type="DUPLICATE",
    )


def client_a_ambiguous_candidate(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """Two internal payments of the identical amount to the identical
    counterparty on the identical day, and two bank credits that match both
    equally well -- genuinely ambiguous with no principled deterministic
    rule to prefer one pairing over the other. Left unresolved (UNEXPLAINED)
    by the deterministic engine; this is exactly the kind of case M5b's ML
    ranking is meant to improve on later, never something Pass 1-6 should
    guess at."""
    eco_id_1, eco_id_2 = f"CA-AMBIG-{seq:04d}-A", f"CA-AMBIG-{seq:04d}-B"
    amount = Decimal(rng.randrange(20000, 80000)) / 100
    counterparty = "TWIN INVOICE TRADERS"
    txn_date = base_date + timedelta(days=rng.randint(0, 10))

    def _internal(eco_id: str, seq_letter: str) -> dict:
        return _tag({
            "Trade_ID": "", "Txn_Reference": "",
            "Posting_Date": _fmt(txn_date, "%Y-%m-%d"),
            "Amount": str(amount), "Dr_Cr_Indicator": "D",
            "Counterparty_Name": counterparty,
            "Narration": f"NEFT PAYMENT TO {counterparty} (invoice {seq_letter})",
        }, eco_id)

    def _bank(eco_id: str, seq_letter: str) -> dict:
        return _tag({
            "Txn Date": _fmt(txn_date, "%d/%m/%Y"), "Value Date": _fmt(txn_date, "%d/%m/%Y"),
            "Debit": str(amount), "Credit": "", "UTR Number": "", "Chq/Ref No": "",
            "Description": f"NEFT-{counterparty}-{seq_letter}",
        }, eco_id)

    # Both economic events share one scenario record so the evaluation
    # harness can treat this as a single "ambiguous pair" outcome; each
    # instance below is tagged with its own economic_transaction_id, but
    # since either internal row could legitimately pair with either bank
    # row, ground truth intentionally does not assert a specific pairing.
    return Scenario(
        scenario_name="AMBIGUOUS_CANDIDATE", economic_transaction_id=eco_id_1, client_code="client_a",
        rows_by_source={
            "internal_ledger": [_internal(eco_id_1, "A"), _internal(eco_id_2, "B")],
            "bank_statement": [_bank(eco_id_1, "A"), _bank(eco_id_2, "B")],
        },
        expected_exception_type="UNEXPLAINED",
    )


CLIENT_A_SOURCES = ("internal_ledger", "bank_statement")


# ---------------------------------------------------------------------------
# Client B: internal_ledger (CSV) <-> payment_gateway (JSON)
# ---------------------------------------------------------------------------

def client_b_exact_match(seq: int, base_date: date, rng: random.Random) -> Scenario:
    eco_id = f"CB-EXACT-{seq:04d}"
    order_id = f"ORD{200000 + seq}"
    amount = Decimal(rng.randrange(50000, 900000)) / 100
    customer = rng.choice(["R KUMAR", "S PATEL", "A SHARMA", "N REDDY"])
    txn_date = base_date + timedelta(days=rng.randint(0, 20))

    internal_row = _tag({
        "InternalRef": f"INTREF{seq:05d}",
        "OrderId": order_id,
        "PostedOn": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(amount),
        "DrCr": "CR",
        "CustomerName": customer,
        "Notes": f"Order {order_id} settlement due",
    }, eco_id)
    gateway_row = _tag({
        "gateway_txn_id": f"PGTXN{900000 + seq}",
        "order_id": order_id,
        "settled_at": f"{txn_date.isoformat()}T18:30:00",
        "net_amount": str(amount),
        "entry_type": "settlement",
        "merchant_name": customer,
        "remarks": f"settlement for {order_id}",
    }, eco_id)
    return Scenario(
        scenario_name="EXACT_IDENTIFIER_MATCH",
        economic_transaction_id=eco_id,
        client_code="client_b",
        rows_by_source={"internal_ledger": [internal_row], "payment_gateway": [gateway_row]},
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "payment_gateway"]},
    )


def client_b_fee_adjusted_settlement(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """This particular gateway settlement record type doesn't carry order_id
    at all (an aggregate/batch settlement style, foreshadowing M4's
    aggregation work) -- nothing links the two sides by reference, so this
    can only be resolved by Pass 5 computing gross - fee - tax(fee) and
    finding it matches the observed net within tolerance."""
    eco_id = f"CB-FEETAX-{seq:04d}"
    gross = Decimal(rng.randrange(500000, 2000000)) / 100  # large gross so 2%+18%-of-fee is unambiguous
    fee = (gross * Decimal("2.0") / Decimal(100)).quantize(Decimal("0.01"))
    tax_on_fee = (fee * Decimal("18.0") / Decimal(100)).quantize(Decimal("0.01"))
    net = gross - fee - tax_on_fee
    customer = rng.choice(["R KUMAR", "S PATEL", "A SHARMA", "N REDDY"])
    txn_date = base_date + timedelta(days=rng.randint(0, 20))

    internal_row = _tag({
        "InternalRef": f"INTREF{seq:05d}",
        "OrderId": "",
        "PostedOn": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(gross),
        "DrCr": "CR",
        "CustomerName": customer,
        "Notes": "Provisional collection, gateway fee to be deducted on settlement",
    }, eco_id)
    gateway_row = _tag({
        "gateway_txn_id": f"PGBATCH{900000 + seq}",
        "order_id": "",
        "settled_at": f"{txn_date.isoformat()}T18:30:00",
        "net_amount": str(net),
        "entry_type": "settlement",
        "merchant_name": customer,
        "remarks": "aggregate settlement, fee and GST on fee deducted",
    }, eco_id)
    return Scenario(
        scenario_name="FEE_ADJUSTED_SETTLEMENT",
        economic_transaction_id=eco_id,
        client_code="client_b",
        rows_by_source={"internal_ledger": [internal_row], "payment_gateway": [gateway_row]},
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "payment_gateway"]},
    )


def client_b_bundled_settlement_many_to_one(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """Several customer orders bundled into one daily gateway settlement
    record -- no per-order ORDER_ID on the settlement side, and no single
    order's amount matches the bundle, so only Pass 6 (aggregation via
    SETTLEMENT_BATCH_REF) can resolve this: 3 internal : 1 external."""
    eco_id = f"CB-BUNDLE-{seq:04d}"
    batch_ref = f"BATCHB{800000 + seq}"
    txn_date = base_date + timedelta(days=rng.randint(0, 15))
    customers = ["R KUMAR", "S PATEL", "A SHARMA"]
    amounts = [Decimal(rng.randrange(20000, 150000)) / 100 for _ in customers]

    internal_rows = []
    for i, (customer, amount) in enumerate(zip(customers, amounts), start=1):
        internal_rows.append(_tag({
            "InternalRef": f"INTREF-BUNDLE-{seq:04d}-{i}", "OrderId": "",
            "PostedOn": _fmt(txn_date, "%Y-%m-%d"),
            "Amount": str(amount), "DrCr": "CR", "CustomerName": customer,
            "Notes": f"Order settlement due, batch {batch_ref}",
            "SettlementBatchRef": batch_ref,
        }, eco_id))

    gateway_row = _tag({
        "gateway_txn_id": f"PGBATCH{950000 + seq}", "order_id": "",
        "settled_at": f"{txn_date.isoformat()}T20:00:00",
        "net_amount": str(sum(amounts)),
        "entry_type": "settlement", "merchant_name": "BUNDLED SETTLEMENT",
        "remarks": f"bundled settlement for batch {batch_ref}",
        "batch_ref": batch_ref,
    }, eco_id)

    return Scenario(
        scenario_name="BUNDLED_SETTLEMENT_MANY_TO_ONE",
        economic_transaction_id=eco_id,
        client_code="client_b",
        rows_by_source={"internal_ledger": internal_rows, "payment_gateway": [gateway_row]},
        expected_cardinality="MANY_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "payment_gateway"]},
    )


def client_b_reference_matched_unexplained_variance(seq: int, base_date: date, rng: random.Random) -> Scenario:
    """Order_id matches cleanly (Pass 1 resolves this as EXACT_REFERENCE,
    since Pass 1/2 never check amount at all), but the gateway's net amount
    reflects a flat deduction that does NOT match the configured 2% MDR +
    18% GST-on-fee formula -- the settlement module (M6) must flag this as
    an unexplained variance rather than silently accepting or explaining it
    away."""
    eco_id = f"CB-UNEXPLAINED-{seq:04d}"
    order_id = f"ORDVAR{300000 + seq}"
    gross = Decimal(rng.randrange(500000, 1500000)) / 100
    flat_unexplained_deduction = Decimal("150.00")  # does not match the 2%+18%-of-fee formula
    net = gross - flat_unexplained_deduction
    customer = rng.choice(["R KUMAR", "S PATEL"])
    txn_date = base_date + timedelta(days=rng.randint(0, 15))

    internal_row = _tag({
        "InternalRef": f"INTREF-VAR-{seq:05d}", "OrderId": order_id,
        "PostedOn": _fmt(txn_date, "%Y-%m-%d"),
        "Amount": str(gross), "DrCr": "CR", "CustomerName": customer,
        "Notes": f"Order {order_id} settlement due",
    }, eco_id)
    gateway_row = _tag({
        "gateway_txn_id": f"PGTXNVAR{960000 + seq}", "order_id": order_id,
        "settled_at": f"{txn_date.isoformat()}T18:30:00",
        "net_amount": str(net), "entry_type": "settlement", "merchant_name": customer,
        "remarks": f"settlement for {order_id}, includes an undocumented deduction",
    }, eco_id)
    return Scenario(
        scenario_name="REFERENCE_MATCHED_UNEXPLAINED_VARIANCE",
        economic_transaction_id=eco_id,
        client_code="client_b",
        rows_by_source={"internal_ledger": [internal_row], "payment_gateway": [gateway_row]},
        expected_cardinality="ONE_TO_ONE",
        expected_match_group={"sources": ["internal_ledger", "payment_gateway"]},
    )


CLIENT_B_SOURCES = ("internal_ledger", "payment_gateway")
