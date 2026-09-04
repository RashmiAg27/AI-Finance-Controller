import re
from datetime import datetime, date
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

_ROUNDING = {"HALF_UP": ROUND_HALF_UP, "HALF_EVEN": ROUND_HALF_EVEN}
_STRING_OPS = {
    "trim": lambda s: s.strip(),
    "uppercase": lambda s: s.upper(),
    "lowercase": lambda s: s.lower(),
    "collapse_whitespace": lambda s: re.sub(r"\s+", " ", s).strip(),
    "strip_non_alphanumeric": lambda s: re.sub(r"[^A-Za-z0-9]", "", s),
}


def apply_string_operations(value: str, operations: list[str]) -> str:
    result = value
    for op in operations:
        fn = _STRING_OPS.get(op)
        if fn is None:
            raise ValueError(f"unknown normalization operation: {op!r}")
        result = fn(result)
    return result


def parse_date(value: str, date_format: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, date_format).date()


def parse_decimal(value: str, sign_convention: str | None) -> Decimal | None:
    value = (value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        magnitude = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"cannot parse decimal from {value!r}") from exc

    if sign_convention == "debit_negative":
        return -abs(magnitude)
    if sign_convention == "credit_positive":
        return abs(magnitude)
    return magnitude  # "signed" or None: trust the source value's own sign


def round_decimal(value: Decimal, decimal_places: int, rounding: str) -> Decimal:
    quantum = Decimal(1).scaleb(-decimal_places)
    return value.quantize(quantum, rounding=_ROUNDING.get(rounding, ROUND_HALF_UP))
