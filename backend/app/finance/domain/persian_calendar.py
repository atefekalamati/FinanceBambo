"""Gregorian <-> Persian (Jalali) conversion for monthly financial bucketing.

The frontend buckets months with `Intl.DateTimeFormat("en-US-u-ca-persian")`, so a
month boundary the backend disagrees about would move money between bars on the chart.
These functions reproduce ICU's arithmetic Persian calendar exactly. `tests/
persian_calendar_golden.py` holds every month boundary ICU reports from 1394-11 to
1420-10, and the suite checks each one — those are the days a disagreement would move
money across. The full day-by-day diff over 1990-2050 was run once during development
and agreed on all 22280 days, but it is the golden boundaries that CI enforces.

No dependency is added for this: the conversion is a few dozen lines of integer
arithmetic, and pulling in a calendar package to run it would be the larger change.
"""

from datetime import date

_GREGORIAN_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def gregorian_to_persian(value: date) -> tuple[int, int, int]:
    """Return the Persian (year, month, day) that `value` falls on. Month is 1..12."""
    gregorian_year, month, day = value.year, value.month, value.day
    if gregorian_year > 1600:
        persian_year = 979
        gregorian_year -= 1600
    else:
        persian_year = 0
        gregorian_year -= 621
    leap_reference = gregorian_year + 1 if month > 2 else gregorian_year
    days = (
        365 * gregorian_year
        + (leap_reference + 3) // 4
        - (leap_reference + 99) // 100
        + (leap_reference + 399) // 400
        - 80
        + day
        + _GREGORIAN_DAYS_BEFORE_MONTH[month - 1]
    )
    persian_year += 33 * (days // 12053)
    days %= 12053
    persian_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        persian_year += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return persian_year, 1 + days // 31, 1 + days % 31
    return persian_year, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def persian_to_gregorian(persian_year: int, persian_month: int, persian_day: int) -> date:
    """Inverse of `gregorian_to_persian`. Raises ValueError on an impossible month."""
    if not 1 <= persian_month <= 12:
        raise ValueError("persian month must be between 1 and 12")
    if persian_year > 979:
        gregorian_year = 1600
        persian_year -= 979
    else:
        gregorian_year = 621
    days = (
        365 * persian_year
        + (persian_year // 33) * 8
        + (persian_year % 33 + 3) // 4
        + 78
        + persian_day
        + ((persian_month - 1) * 31 if persian_month < 7 else (persian_month - 7) * 30 + 186)
    )
    gregorian_year += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gregorian_year += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gregorian_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gregorian_year += (days - 1) // 365
        days = (days - 1) % 365
    day = days + 1
    leap = (gregorian_year % 4 == 0 and gregorian_year % 100 != 0) or gregorian_year % 400 == 0
    lengths = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    month = 0
    while month < 12 and day > lengths[month]:
        day -= lengths[month]
        month += 1
    return date(gregorian_year, month + 1, day)


def previous_persian_month(persian_year: int, persian_month: int) -> tuple[int, int]:
    return (persian_year - 1, 12) if persian_month == 1 else (persian_year, persian_month - 1)


def next_persian_month(persian_year: int, persian_month: int) -> tuple[int, int]:
    return (persian_year + 1, 1) if persian_month == 12 else (persian_year, persian_month + 1)


def persian_month_window(anchor: date, month_count: int) -> tuple[date, int, int]:
    """The `month_count` Persian months ending on the month containing `anchor`.

    Returns the Gregorian date the window opens on, plus the first month's year and
    month. The window closes on `anchor` itself, not the end of its Persian month, so
    the series never reports cost dated after the reporting date.
    """
    if month_count < 1:
        raise ValueError("month_count must be positive")
    year, month, _ = gregorian_to_persian(anchor)
    for _ in range(month_count - 1):
        year, month = previous_persian_month(year, month)
    if year < 1:
        # A reporting date near the Gregorian epoch walks the window back past Persian
        # year 1. Refusing here keeps it a rejected request rather than a ValueError
        # from date() or a response the DTO cannot represent.
        raise ValueError("reporting date is before the supported calendar range")
    return persian_to_gregorian(year, month, 1), year, month
