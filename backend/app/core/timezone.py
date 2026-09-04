"""Display-timezone conversion -- the one place +05:30-style arithmetic is
allowed to happen, and even here it never happens as arithmetic: conversion
goes through the IANA tz database (via zoneinfo) so DST and any future rule
change are handled for free, not by adding a fixed offset.

Every timestamp stored by this app is UTC (see app.db.types.UTCDateTime).
This module exists solely to answer "what wall-clock time was that for a
given client", never to change what is stored -- a display timezone changes
how an EVENT TIME is shown, never the event time itself, and never a
BUSINESS DATE (trade_date, settlement_date, business_date, ...), which is a
plain calendar date with no time-of-day or timezone component at all and
must never be shifted by this conversion.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_DISPLAY_TIMEZONE = "Asia/Kolkata"


def to_display_timezone(value: datetime, tz_name: str = DEFAULT_DISPLAY_TIMEZONE) -> datetime:
    """Converts a UTC (or otherwise tz-aware) instant to the given IANA zone.

    Raises on a naive `value` rather than guessing its zone -- an event time
    with no timezone attached is a bug at the point it was created, not
    something this function should paper over.
    """
    if value.tzinfo is None:
        raise ValueError(f"cannot convert naive datetime {value!r} to a display timezone")
    return value.astimezone(ZoneInfo(tz_name))
