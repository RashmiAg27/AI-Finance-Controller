from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core.timezone import DEFAULT_DISPLAY_TIMEZONE


def _format_event_time(value: datetime, tz_name: str) -> str:
    """An EVENT TIME (created_at, closed_at, ...) is handed to the agent
    already converted to the client's local display time and formatted as a
    string it should quote verbatim -- the model must never see a raw UTC
    timestamp or attempt its own timezone arithmetic (see the system prompt).
    Every persisted timestamp is tz-aware UTC (app.db.types.UTCDateTime), so
    the naive-input branch below only guards against something upstream
    having gone wrong, never normal operation."""
    if value.tzinfo is None:
        return value.isoformat()
    local = value.astimezone(ZoneInfo(tz_name))
    return f"{local.strftime('%d %b %Y, %I:%M:%S %p')} {local.tzname()}"


def to_jsonable(value, *, display_timezone: str = DEFAULT_DISPLAY_TIMEZONE):
    """Recursively converts Decimal/date/datetime (and SQLAlchemy-adjacent
    plain containers) into JSON-safe primitives so tool results can be
    serialized straight into a tool_result content block.

    datetime and date are handled distinctly on purpose -- datetime is
    checked first because it is itself a `date` subclass. A datetime is an
    EVENT TIME and is localized (see _format_event_time); a plain date is a
    BUSINESS DATE (transaction_date, value_date, business_date, ...) with no
    time-of-day or timezone component at all, and is never converted or
    shifted -- it round-trips as the same calendar date regardless of
    display timezone.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _format_event_time(value, display_timezone)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: to_jsonable(v, display_timezone=display_timezone) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v, display_timezone=display_timezone) for v in value]
    return value
