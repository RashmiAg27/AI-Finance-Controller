from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.core.errors import IngestionError
from app.domains.normalization import value_normalizers as vn
from app.schemas.config import DataSourceConfig, FieldMapping


@dataclass
class MappedRecord:
    transaction_date: date | None = None
    value_date: date | None = None
    settlement_date: date | None = None
    amount: Decimal | None = None
    debit_credit: str | None = None
    counterparty: str | None = None
    counterparty_type: str | None = None
    counterparty_account: str | None = None
    account: str | None = None
    description: str | None = None
    status: str | None = None
    payment_method: str | None = None
    fee_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    adjustment_amount: Decimal | None = None
    identifiers: dict[str, str] = field(default_factory=dict)  # identifier_type -> raw value
    static_fields: dict[str, str] = field(default_factory=dict)
    raw_row_text: str = ""  # concatenation of all raw values, used by classification's any_field_contains


_DATE_FIELDS = {"transaction_date", "value_date", "settlement_date"}

# Decimal-valued canonical fields other than `amount`. They are single-valued
# (unlike amount, which a bank statement splits across a debit and a credit
# column), so each simply parses into its own attribute.
_DECIMAL_FIELDS = {"fee_amount", "tax_amount", "adjustment_amount"}


def _apply_value_map(raw_value: str, value_map: dict[str, str] | None) -> str:
    if not value_map:
        return raw_value
    return value_map.get(raw_value, raw_value)


def map_record(raw_data: dict, ds_config: DataSourceConfig, *, row_context: str) -> MappedRecord:
    result = MappedRecord(static_fields=dict(ds_config.static_fields))
    result.raw_row_text = " | ".join(str(v) for v in raw_data.values())

    amount_parts: list[Decimal] = []

    for fm in ds_config.field_mappings:
        raw_value = raw_data.get(fm.source_field, "")
        raw_value = "" if raw_value is None else str(raw_value)

        if fm.required and not raw_value.strip():
            raise IngestionError(
                f"{row_context}: required field {fm.source_field!r} (-> {fm.canonical_field}) is empty"
            )
        if not raw_value.strip():
            continue

        if fm.canonical_field in _DATE_FIELDS:
            try:
                parsed_date = vn.parse_date(raw_value, fm.date_format or "%Y-%m-%d")
            except ValueError as exc:
                raise IngestionError(f"{row_context}: {exc}") from exc
            setattr(result, fm.canonical_field, parsed_date)

        elif fm.canonical_field == "amount":
            try:
                parsed_amount = vn.parse_decimal(raw_value, fm.sign_convention)
            except ValueError as exc:
                raise IngestionError(f"{row_context}: {exc}") from exc
            if parsed_amount is not None:
                amount_parts.append(parsed_amount)

        elif fm.canonical_field == "identifier":
            result.identifiers[fm.identifier_type] = raw_value

        elif fm.canonical_field in _DECIMAL_FIELDS:
            try:
                parsed = vn.parse_decimal(raw_value, fm.sign_convention)
            except ValueError as exc:
                raise IngestionError(f"{row_context}: {exc}") from exc
            if parsed is not None:
                setattr(result, fm.canonical_field, abs(parsed))

        elif fm.canonical_field == "debit_credit":
            result.debit_credit = _apply_value_map(raw_value, fm.value_map)

        else:  # counterparty | counterparty_type | counterparty_account
               # | account | description | status | payment_method
            setattr(result, fm.canonical_field, _apply_value_map(raw_value, fm.value_map))

    if amount_parts:
        result.amount = sum(amount_parts)

    return result
