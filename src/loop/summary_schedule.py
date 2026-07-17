"""Local-time schedule policy for trip overview notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time

from src.config.timezone import LOCAL_TIMEZONE


SUMMARY_HOURS = (9, 21)


@dataclass(frozen=True)
class SummarySlot:
    """A reached overview slot in the application's local timezone."""

    local_date: date
    hour: int

    def __post_init__(self) -> None:
        if not isinstance(self.local_date, date) or isinstance(self.local_date, datetime):
            raise ValueError("Summary slot local_date must be a date.")
        if self.hour not in SUMMARY_HOURS:
            raise ValueError("Summary slot hour must be a configured summary hour.")


def latest_due_summary_slot(now: datetime) -> SummarySlot | None:
    """Return the most recent 09:00 or 21:00 slot reached in Europe/Berlin."""

    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime.")
    local_now = (
        now.replace(tzinfo=LOCAL_TIMEZONE)
        if now.tzinfo is None or now.utcoffset() is None
        else now.astimezone(LOCAL_TIMEZONE)
    )
    reached_hours = tuple(
        hour for hour in SUMMARY_HOURS if local_now.time() >= datetime_time(hour)
    )
    if not reached_hours:
        return None
    return SummarySlot(local_now.date(), reached_hours[-1])
