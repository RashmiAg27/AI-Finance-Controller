"""Proves the one place this app is allowed to do +05:30-shaped conversion
(app.core.timezone.to_display_timezone) does it via the IANA tz database, not
fixed-offset arithmetic -- including the date-boundary cases where the two
would disagree if DST or a future rule change ever applied."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.timezone import DEFAULT_DISPLAY_TIMEZONE, to_display_timezone


def test_default_display_timezone_is_asia_kolkata():
    assert DEFAULT_DISPLAY_TIMEZONE == "Asia/Kolkata"


def test_utc_to_ist_is_exactly_five_hours_thirty_minutes_ahead():
    utc = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    ist = to_display_timezone(utc)

    assert ist.utcoffset().total_seconds() == 5.5 * 3600
    assert (ist.replace(tzinfo=None) - utc.replace(tzinfo=None)).total_seconds() == 5.5 * 3600
    assert ist.hour == 15 and ist.minute == 30 and ist.day == 15


@pytest.mark.parametrize(
    "utc_iso, expected_ist_iso",
    [
        # Well inside the same calendar day on both sides.
        ("2026-01-15T10:00:00+00:00", "2026-01-15T15:30:00+05:30"),
        # The exact instant IST rolls over to the next date: 18:30 UTC is
        # midnight IST. One minute either side of it must land on a
        # different IST calendar date.
        ("2026-01-15T18:29:00+00:00", "2026-01-15T23:59:00+05:30"),
        ("2026-01-15T18:30:00+00:00", "2026-01-16T00:00:00+05:30"),
        ("2026-01-15T18:31:00+00:00", "2026-01-16T00:01:00+05:30"),
        # A UTC date that is already the next day relative to IST's
        # afternoon -- the reverse-direction boundary.
        ("2026-01-15T23:59:00+00:00", "2026-01-16T05:29:00+05:30"),
        # A year-end boundary, so the date rollover crosses a month AND a
        # year, not just a day-of-month.
        ("2025-12-31T19:00:00+00:00", "2026-01-01T00:30:00+05:30"),
    ],
)
def test_utc_to_ist_date_boundaries(utc_iso: str, expected_ist_iso: str):
    utc = datetime.fromisoformat(utc_iso)
    ist = to_display_timezone(utc)
    assert ist.isoformat() == expected_ist_iso


def test_converts_from_a_non_utc_input_zone_too():
    """Not merely "UTC + fixed offset" -- any aware datetime, regardless of
    its own zone, converts to the correct Asia/Kolkata wall-clock time."""
    eastern = datetime(2026, 6, 1, 9, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    ist = to_display_timezone(eastern)
    # 09:00 EDT (UTC-4 in June) == 13:00 UTC == 18:30 IST.
    assert ist.isoformat() == "2026-06-01T18:30:00+05:30"


def test_naive_datetime_is_rejected_not_guessed():
    with pytest.raises(ValueError, match="naive datetime"):
        to_display_timezone(datetime(2026, 1, 1, 12, 0, 0))


def test_a_different_iana_zone_can_be_requested_explicitly():
    utc = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    tokyo = to_display_timezone(utc, "Asia/Tokyo")
    assert tokyo.isoformat() == "2026-01-15T19:00:00+09:00"
