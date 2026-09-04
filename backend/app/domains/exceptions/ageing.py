from datetime import datetime

from app.core.clock import Clock, default_clock


def exception_age_days(first_seen_at: datetime, *, clock: Clock = default_clock) -> int:
    return (clock.now() - first_seen_at).days


def severity_for_age(age_days: int, thresholds: dict[str, int]) -> str:
    """thresholds is the client-configured exception_rules.ageing_thresholds_days
    (e.g. {LOW: 3, MEDIUM: 7, HIGH: 15, CRITICAL: 30}) -- never a hardcoded
    universal ageing rule."""
    if age_days >= thresholds.get("CRITICAL", 30):
        return "CRITICAL"
    if age_days >= thresholds.get("HIGH", 15):
        return "HIGH"
    if age_days >= thresholds.get("MEDIUM", 7):
        return "MEDIUM"
    return "LOW"
