"""The kinds of reconciliation this platform performs.

"Cash reconciliation" is not one comparison. It is the family of proofs below,
each answering a different question about the same money, and each with a
different pair of sides, a different natural key, and a different reason a
difference might be legitimate. Treating them as one thing is what produces
the classic false break: a ₹10,000 sale against a ₹9,764 bank credit is not a
mismatch, it is a settlement whose fee and GST were never modelled.

The order below is roughly the order money travels: from the transaction that
created it, through settlement, into the bank, and out again as tax.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationType:
    code: str
    label: str
    left_side: str
    right_side: str
    natural_key: str
    legitimate_differences: str
    scoped_to_account: bool


RECONCILIATION_TYPES: tuple[ReconciliationType, ...] = (
    ReconciliationType(
        code="BANK_GL",
        label="Bank ↔ General Ledger",
        left_side="Bank account statement",
        right_side="General ledger / cash book for that account",
        natural_key="UTR, cheque number or bank reference; else amount + value date",
        legitimate_differences=(
            "Timing: a cheque issued but not presented, or a credit dated on the value date "
            "rather than the posting date."
        ),
        scoped_to_account=True,
    ),
    ReconciliationType(
        code="BANK_AR",
        label="Bank ↔ Accounts Receivable",
        left_side="Bank credits",
        right_side="Customer receipts and open invoices",
        natural_key="Invoice number or UTR in the narration; else amount + customer",
        legitimate_differences=(
            "TDS withheld by the customer, bank charges deducted in transit, a credit note, "
            "or a deliberate part payment. A short receipt is not automatically a break."
        ),
        scoped_to_account=True,
    ),
    ReconciliationType(
        code="BANK_AP",
        label="Bank ↔ Accounts Payable",
        left_side="Bank debits",
        right_side="Vendor payments and open invoices",
        natural_key="UTR, or payment reference and invoice number",
        legitimate_differences="TDS deducted at source, so the bank debit is the invoice net of tax.",
        scoped_to_account=True,
    ),
    ReconciliationType(
        code="PAYMENT_SETTLEMENT",
        label="Payments ↔ Settlement batch",
        left_side="Individual UPI / card / netbanking transactions",
        right_side="The aggregator's settlement report",
        natural_key="Payment id, order id, or the settlement id the report groups them under",
        legitimate_differences=(
            "The settlement is the gross of many payments less MDR, GST on MDR, refunds and "
            "chargebacks -- it will never equal the gross."
        ),
        scoped_to_account=False,
    ),
    ReconciliationType(
        code="SETTLEMENT_BANK",
        label="Settlement ↔ Bank credit",
        left_side="Settlement report net amount",
        right_side="Bank credit in the settlement account",
        natural_key="Settlement UTR",
        legitimate_differences="Value-date timing when the credit lands the next working day.",
        scoped_to_account=True,
    ),
    ReconciliationType(
        code="INTERNAL_TRANSFER",
        label="Internal transfer / sweep",
        left_side="Debit in the source account",
        right_side="Credit in the destination account",
        natural_key="UTR, or amount + date across the two accounts",
        legitimate_differences=(
            "Same-day timing between the two legs. Crucially this movement changes where the "
            "money sits, not how much there is -- it must never be counted as a cash outflow."
        ),
        scoped_to_account=False,
    ),
    ReconciliationType(
        code="TAX_PAYMENT",
        label="Tax liability ↔ Bank",
        left_side="GST / TDS liability for the period",
        right_side="Challan and the corresponding bank debit",
        natural_key="Challan number (CIN / BSR + serial)",
        legitimate_differences="Liability discharged partly from input credit rather than from cash.",
        scoped_to_account=True,
    ),
    ReconciliationType(
        code="TDS",
        label="TDS deduction chain",
        left_side="Invoice gross",
        right_side="Net vendor payment + TDS payable + government remittance",
        natural_key="Invoice number, then the TDS challan",
        legitimate_differences=(
            "By design the bank payment is short by exactly the TDS. The reconciliation proves "
            "the deduction was remitted, not that the amounts are equal."
        ),
        scoped_to_account=False,
    ),
    ReconciliationType(
        code="CHARGEBACK",
        label="Chargeback / dispute",
        left_side="The original card payment",
        right_side="The later settlement adjustment and bank debit",
        natural_key="ARN or original payment id",
        legitimate_differences=(
            "The debit arrives days or weeks after the payment, so it belongs to an earlier "
            "period's transaction, not to the day it lands."
        ),
        scoped_to_account=False,
    ),
    ReconciliationType(
        code="EXCHANGE_CLEARING",
        label="Exchange / clearing obligation",
        left_side="Trades and the clearing corporation's obligation file",
        right_side="Settlement instruction and the bank movement",
        natural_key="Trade id, settlement number",
        legitimate_differences="Brokerage, STT, stamp duty, exchange charges and GST on brokerage.",
        scoped_to_account=True,
    ),
)

BY_CODE = {t.code: t for t in RECONCILIATION_TYPES}
CODES = tuple(t.code for t in RECONCILIATION_TYPES)


def describe(code: str) -> dict:
    rtype = BY_CODE.get(code)
    if rtype is None:
        return {"code": code, "label": code, "known": False}
    return {
        "code": rtype.code,
        "label": rtype.label,
        "left_side": rtype.left_side,
        "right_side": rtype.right_side,
        "natural_key": rtype.natural_key,
        "legitimate_differences": rtype.legitimate_differences,
        "scoped_to_account": rtype.scoped_to_account,
        "known": True,
    }


def catalogue() -> list[dict]:
    return [describe(code) for code in CODES]
