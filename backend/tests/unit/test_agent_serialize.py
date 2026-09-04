"""app.agent.serialize.to_jsonable is where a tool result crosses from
"whatever Python objects the domain layer produced" into "what the LLM is
handed" -- these tests prove an EVENT TIME (datetime) arrives already
localized as a display string (so the model never does its own timezone
arithmetic, see the system prompt), while a BUSINESS DATE (date) is left as
a plain calendar date, untouched by any timezone conversion."""
from datetime import date, datetime, timezone
from decimal import Decimal

from app.agent.serialize import to_jsonable


def test_datetime_is_converted_to_a_localized_display_string():
    utc = datetime(2026, 9, 4, 14, 53, 43, tzinfo=timezone.utc)
    result = to_jsonable({"created_at": utc})
    assert result["created_at"] == "04 Sep 2026, 08:23:43 PM IST"


def test_business_date_is_left_as_a_plain_calendar_date():
    result = to_jsonable({"business_date": date(2026, 9, 4)})
    assert result["business_date"] == "2026-09-04"


def test_a_different_display_timezone_can_be_requested():
    utc = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    result = to_jsonable({"at": utc}, display_timezone="Asia/Tokyo")
    assert result["at"] == "15 Jan 2026, 07:00:00 PM JST"


def test_decimal_and_nested_structures_still_serialize_correctly():
    result = to_jsonable({
        "amount": Decimal("1205.21"),
        "items": [{"transaction_date": date(2026, 9, 4), "closed_at": datetime(2026, 9, 4, 15, 41, 34, tzinfo=timezone.utc)}],
    })
    assert result["amount"] == "1205.21"
    assert result["items"][0]["transaction_date"] == "2026-09-04"
    assert result["items"][0]["closed_at"] == "04 Sep 2026, 09:11:34 PM IST"
