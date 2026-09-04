"""Short-term cash forecast. Deliberately simple and explainable (spec
section 21: avoid pretending synthetic data supports a production-grade
forecast) -- a point estimate from the current CashPosition's own components,
with an uncertainty band sized directly by that position's honestly-computed
unreconciled_amount rather than any modeled probability distribution.

This is a prototype assumption, not a statistical forecast model, and is
labeled as such on every record.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.cash import CashForecast, CashPosition

_ASSUMPTIONS_NOTE = (
    "Prototype short-term forecast: expected_value = confirmed_cash + expected_inflows - "
    "expected_outflows from the current cash position. The low/high band is sized by "
    "unreconciled_amount (today's total open-exception exposure) applied symmetrically -- "
    "this is a simple, explainable heuristic, not a statistical or ML forecasting model, "
    "and has not been back-tested against real settlement-delay data."
)


def build_forecast(db: Session, cash_position: CashPosition, *, horizon_days: int = 7) -> CashForecast:
    expected_value = (
        cash_position.confirmed_cash + cash_position.expected_inflows - cash_position.expected_outflows
    )
    band = cash_position.unreconciled_amount

    forecast = CashForecast(
        client_id=cash_position.client_id, cash_position_id=cash_position.id,
        horizon_days=horizon_days, as_of=date.today() + timedelta(days=horizon_days),
        expected_value=expected_value, low_estimate=expected_value - band, high_estimate=expected_value + band,
        drivers={
            "confirmed_cash": str(cash_position.confirmed_cash),
            "expected_inflows": str(cash_position.expected_inflows),
            "expected_outflows": str(cash_position.expected_outflows),
            "unreconciled_amount": str(cash_position.unreconciled_amount),
            "pending_cash_excluded_from_point_estimate": str(cash_position.pending_cash),
        },
        assumptions_note=_ASSUMPTIONS_NOTE,
    )
    db.add(forecast)
    db.flush()
    return forecast
