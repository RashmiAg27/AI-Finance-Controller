from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class TransactionIdentifierResponse(BaseModel):
    identifier_type: str
    value_raw: str
    value_normalized: str
    is_primary: bool
    linked_via_rule_id: str | None

    model_config = {"from_attributes": True}


class TransactionResponse(BaseModel):
    id: str
    client_id: str
    batch_id: str
    source_id: str
    canonical_reference: str | None
    transaction_type: str
    instrument_type: str
    transaction_date: date
    value_date: date | None
    settlement_date: date | None
    amount: Decimal
    currency: str
    debit_credit: str
    counterparty: str | None
    account: str | None
    description: str | None
    status: str
    source_system: str
    created_at: datetime
    metadata_json: dict = {}
    identifiers: list[TransactionIdentifierResponse] = []

    model_config = {"from_attributes": True}
