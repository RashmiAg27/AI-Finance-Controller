from datetime import datetime, timezone


class Clock:
    """Injectable now() so tests can freeze time (needed for deterministic ageing/reproducibility checks)."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


default_clock = Clock()
