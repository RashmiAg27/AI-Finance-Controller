from decimal import Decimal

from app.schemas.config import AmountTolerance


def tolerance_amount(base: Decimal, tolerance: AmountTolerance) -> Decimal:
    if tolerance.type == "percentage":
        return (base * Decimal(str(tolerance.value)) / Decimal(100)).copy_abs()
    return Decimal(str(tolerance.value))
