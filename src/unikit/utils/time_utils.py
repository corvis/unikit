#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime

from unikit.utils.types import TAnyDate


def datetime_now() -> datetime.datetime:
    """Return `now` in UTC."""
    return datetime.datetime.now(tz=datetime.timezone.utc)


def get_midnight(date: datetime.datetime | None = None) -> datetime.datetime:
    """Return datetime pointing to the midnight of the given date or today."""
    return (date or datetime_now()).replace(hour=0, minute=0, second=0, microsecond=0)


def last_day_of_month(date_: TAnyDate) -> TAnyDate:
    """Return the last day of the month for the given date."""
    if date_.month == 12:
        return date_.replace(day=31)
    return date_.replace(month=date_.month + 1, day=1) - datetime.timedelta(days=1)


def first_day_of_month(d: TAnyDate) -> TAnyDate:
    """Return the first day of the month for the given date."""
    return d.replace(day=1)


def first_day_of_next_month(date: TAnyDate) -> TAnyDate:
    """Return the first day of the next month for the given date."""
    return last_day_of_month(date) + datetime.timedelta(days=1)


def get_month_boundaries(month: datetime.datetime) -> tuple[datetime.datetime, datetime.datetime]:
    """Return tuple of the earliest and the latest passed month datetimes."""
    earliest = first_day_of_month(month).replace(hour=0, minute=0, second=0, microsecond=0)
    latest = last_day_of_month(month).replace(hour=23, minute=59, second=59, microsecond=999999)
    return earliest, latest
