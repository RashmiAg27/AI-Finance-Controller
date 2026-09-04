"""next_business_date() stamps a new run with "today" in the CLIENT's
business calendar. A server clocked in UTC (the common case) is still on
the previous calendar date for the first 5.5 hours of every IST business
day -- 00:00-05:29 IST is 18:30-23:59 UTC the day before -- so computing
"today" from the server's own local date (as this used to do via
date.today()) would silently misdate a batch created in that window. These
tests freeze the clock on both sides of that exact boundary and prove the
business date follows the client's timezone, not the server's."""
from datetime import datetime, timezone

from app.core.clock import Clock
from app.domains.batches import definitions as definitions_service
from app.domains.clients import service as client_service
from app.models.batch_definition import BatchDefinition


class _FrozenClock(Clock):
    def __init__(self, fixed: datetime):
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


def _make_definition(db_session, client) -> BatchDefinition:
    definition = BatchDefinition(client_id=client.id, code="TEST_BATCH", name="Test batch")
    db_session.add(definition)
    db_session.flush()
    return definition


def test_business_date_uses_client_timezone_just_before_ist_midnight(db_session, monkeypatch):
    client = client_service.create_client(db_session, code="TZBIZ1", name="Business Date Co")
    db_session.commit()
    definition = _make_definition(db_session, client)

    # 18:29 UTC on the 15th is 23:59 IST on the 15th -- still the 15th.
    frozen = datetime(2026, 1, 15, 18, 29, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(definitions_service, "default_clock", _FrozenClock(frozen))

    assert definitions_service.next_business_date(db_session, definition) == "2026-01-15"


def test_business_date_rolls_over_at_ist_midnight_while_server_utc_date_is_still_yesterday(
    db_session, monkeypatch,
):
    client = client_service.create_client(db_session, code="TZBIZ2", name="Business Date Co 2")
    db_session.commit()
    definition = _make_definition(db_session, client)

    # 18:30 UTC on the 15th is exactly 00:00 IST on the 16th. The server's
    # own local date (if it were UTC) is still the 15th -- the business date
    # must be the 16th regardless.
    frozen = datetime(2026, 1, 15, 18, 30, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(definitions_service, "default_clock", _FrozenClock(frozen))

    assert definitions_service.next_business_date(db_session, definition) == "2026-01-16"


def test_business_date_follows_a_non_default_client_timezone(db_session, monkeypatch):
    client = client_service.create_client(db_session, code="TZBIZ3", name="Tokyo Client")
    client.display_timezone = "Asia/Tokyo"
    db_session.commit()
    definition = _make_definition(db_session, client)

    # 15:30 UTC is 00:30 JST the next day, but only 21:00 IST the same day --
    # proving this genuinely reads the client's own configured zone rather
    # than a hardcoded Asia/Kolkata.
    frozen = datetime(2026, 1, 15, 15, 30, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(definitions_service, "default_clock", _FrozenClock(frozen))

    assert definitions_service.next_business_date(db_session, definition) == "2026-01-16"
