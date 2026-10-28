"""Day type classifiers used to select time dependent parameters."""

from datetime import datetime

__all__ = ["day_type_week", "day_type_workday", "day_type"]


def day_type_week(dt: datetime) -> str:
    """Return the weekday name of `dt`.

    Args:
        dt: Datetime to classify.

    Returns:
        The lowercase weekday name, or `"weekday"` if it cannot be resolved.
    """
    wd = dt.isoweekday() % 7

    if wd == 0:
        return "sunday"
    elif wd == 1:
        return "monday"
    elif wd == 2:
        return "tuesday"
    elif wd == 3:
        return "wednesday"
    elif wd == 4:
        return "thursday"
    elif wd == 5:
        return "friday"
    elif wd == 6:
        return "saturday"
    else:
        return "weekday"


def day_type_workday(dt: datetime) -> str:
    """Return `"weekend"` for Saturday and Sunday, `"weekday"` otherwise.

    Args:
        dt: Datetime to classify.

    Returns:
        Either `"weekend"` or `"weekday"`.
    """
    wd = dt.isoweekday() % 7

    if wd in (0, 6):
        return "weekend"
    else:
        return "weekday"


day_type = day_type_workday
