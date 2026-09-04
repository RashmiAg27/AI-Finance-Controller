"""Custom SQLAlchemy column types.

SQLite has no native timezone-aware datetime type -- everything is stored as
TEXT, and reading a row back in a fresh session drops any tzinfo the Python
value had, silently turning what was a correct UTC instant into a naive
datetime with the same wall-clock digits. That naive value is exactly the
shape a JSON API must never emit: JavaScript's `Date` constructor treats an
offset-less ISO string as LOCAL time, not UTC, so a UTC timestamp serialized
without an offset displays five and a half hours behind Asia/Kolkata -- which
is the bug this type exists to make structurally impossible.

UTCDateTime is the single choke point: every column typed `Mapped[datetime]`
uses it (via Base.type_annotation_map in app.db.base), so a timestamp read
anywhere in the app is guaranteed timezone-aware UTC, and a naive datetime
handed to it for storage is rejected rather than silently accepted -- the
only correct value to persist ever comes from app.core.clock.default_clock.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Stores any tz-aware datetime as UTC; always returns a UTC tz-aware
    datetime on read, regardless of what the underlying dialect natively
    supports (SQLite has no real timezone-aware type)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                f"naive datetime {value!r} cannot be persisted -- timestamps must be "
                "timezone-aware (use app.core.clock.default_clock.now(), never a bare "
                "datetime.now()/datetime.utcnow())"
            )
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        # SQLite hands back a naive datetime (see module docstring above);
        # every other supported dialect already returns a tz-aware UTC value
        # here, so this branch is a no-op for them and a correctness fix for
        # SQLite specifically.
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
