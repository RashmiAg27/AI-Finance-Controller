"""Proves the actual root cause of the reported bug is fixed: SQLite has no
native timezone-aware column type, and reading a row back in a fresh session
used to silently drop the tzinfo a tz-aware write had -- turning a correct
UTC instant into a naive value with the same digits, which is exactly the
shape that displays hours off once it reaches a browser (see
app.db.types.UTCDateTime for the full explanation). These tests exercise a
real commit + a genuinely separate session, not just the in-memory object,
because the bug only ever showed up on that second read."""
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import StatementError

from app.db.session import SessionLocal
from app.models.client import Client


def test_persisted_datetime_round_trips_as_utc_aware(db_session):
    client = Client(code="TZTEST1", name="Timezone Test Co")
    db_session.add(client)
    db_session.commit()
    client_id = client.id

    # A fresh session, not the one that wrote the row -- SQLAlchemy's
    # identity map on the same session would mask the bug by returning the
    # very Python object that was written, never touching the DB round-trip.
    with SessionLocal() as other_session:
        reloaded = other_session.get(Client, client_id)
        assert reloaded.created_at.tzinfo is not None
        assert reloaded.created_at.utcoffset().total_seconds() == 0
        # ISO serialization (what the API actually sends) must carry an
        # explicit UTC marker, never a bare, offset-less string.
        iso = reloaded.created_at.isoformat()
        assert iso.endswith("+00:00") or iso.endswith("Z")


def test_naive_datetime_is_refused_at_write_time(db_session):
    """A naive datetime must never reach storage silently -- it is refused
    at the point it would be written, not accepted and misinterpreted
    later."""
    client = Client(code="TZTEST2", name="Naive Rejection Co", created_at=datetime(2026, 1, 1))
    db_session.add(client)
    with pytest.raises(StatementError, match="naive datetime"):
        db_session.commit()
    db_session.rollback()


def test_a_non_utc_aware_datetime_is_normalized_to_utc_on_write(db_session):
    from zoneinfo import ZoneInfo

    ist_noon = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    client = Client(code="TZTEST3", name="IST Input Co", created_at=ist_noon)
    db_session.add(client)
    db_session.commit()
    client_id = client.id

    with SessionLocal() as other_session:
        reloaded = other_session.get(Client, client_id)
        assert reloaded.created_at.tzinfo == timezone.utc
        # 12:00 IST (UTC+5:30) is 06:30 UTC.
        assert reloaded.created_at.hour == 6
        assert reloaded.created_at.minute == 30
