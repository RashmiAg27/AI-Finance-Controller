"""Index/bucket builders shared by the matching passes so candidate
generation stays O(N+M) per pass instead of comparing every internal
transaction against every external one."""
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Hashable
from datetime import date
from decimal import Decimal

from app.domains.reconciliation.txn_view import TxnView


def bucket_by(items: list[TxnView], key_fn: Callable[[TxnView], Hashable | None]) -> dict[Hashable, list[TxnView]]:
    buckets: dict[Hashable, list[TxnView]] = {}
    for item in items:
        key = key_fn(item)
        if key is None:
            continue
        buckets.setdefault(key, []).append(item)
    return buckets


def identifier_index(pool: list[TxnView], identifier_type: str) -> dict[str, list[TxnView]]:
    return bucket_by(pool, lambda t: t.identifiers.get(identifier_type) or None)


def suffix_index(pool: list[TxnView], identifier_type: str, suffix_len: int = 6) -> dict[str, list[TxnView]]:
    def key(t: TxnView) -> str | None:
        value = t.identifiers.get(identifier_type)
        return value[-suffix_len:] if value else None

    return bucket_by(pool, key)


def amount_index(pool: list[TxnView]) -> dict[Decimal, list[TxnView]]:
    return bucket_by(pool, lambda t: t.amount)


def amount_instrument_index(pool: list[TxnView]) -> dict[tuple[Decimal, str], list[TxnView]]:
    return bucket_by(pool, lambda t: (t.amount, t.instrument_type))


class AmountSortedPool:
    """External pool sorted by amount so a tolerance window lookup is a
    bisect instead of an O(N) scan per internal transaction."""

    def __init__(self, items: list[TxnView]):
        self._items = sorted(items, key=lambda i: i.amount)
        self._amounts = [i.amount for i in self._items]

    def within(self, center: Decimal, tolerance: Decimal) -> list[TxnView]:
        lo = bisect_left(self._amounts, center - tolerance)
        hi = bisect_right(self._amounts, center + tolerance)
        return self._items[lo:hi]


class DateSortedBucket:
    """A bucket of transactions kept sorted by a date field so a tolerance
    window can be found via bisect instead of scanning the whole bucket."""

    def __init__(self, items: list[TxnView], date_field: str):
        self._date_field = date_field
        self._items = sorted((i for i in items if getattr(i, date_field) is not None),
                              key=lambda i: getattr(i, date_field))
        self._dates = [getattr(i, date_field) for i in self._items]

    def within(self, center: date, tolerance_days: int) -> list[TxnView]:
        lo = bisect_left(self._dates, center.toordinal() - tolerance_days, key=lambda d: d.toordinal()) \
            if self._dates else 0
        hi = bisect_right(self._dates, center.toordinal() + tolerance_days, key=lambda d: d.toordinal()) \
            if self._dates else 0
        return self._items[lo:hi]
