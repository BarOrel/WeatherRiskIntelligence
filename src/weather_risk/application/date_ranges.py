import datetime as dt

from weather_risk.application.errors import InvalidDateRangeError
from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import WeatherDateRange


def historical_date_range(
    start_date: dt.date, end_date: dt.date, *, today: dt.date, max_days: int
) -> WeatherDateRange:
    """Build a range for historical data: ordered, not in the future, at most ``max_days``."""
    try:
        date_range = WeatherDateRange(start=start_date, end=end_date)
    except DomainValidationError as exc:
        raise InvalidDateRangeError(str(exc)) from exc

    if date_range.end > today:
        raise InvalidDateRangeError("Historical data cannot include future dates")
    if date_range.days > max_days:
        raise InvalidDateRangeError(
            f"Date range spans {date_range.days} days; the maximum is {max_days}"
        )
    return date_range
