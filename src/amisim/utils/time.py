"""Time parsing helpers used by retention and cleanup workflows."""

from __future__ import annotations

import datetime
import re


_DURATION_RE = re.compile(r"(\d+)([smhdw])")
_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_age_to_timedelta(value: str) -> datetime.timedelta:
    """Parse a compact age string into ``datetime.timedelta``.

    Supported units are seconds (s), minutes (m), hours (h), days (d),
    and weeks (w). Multiple chunks can be concatenated, for example
    ``"1d12h"`` or ``"2w3d4h"``.

    :param value: Duration expression, e.g. ``"2d"``.
    :return: Parsed duration as ``datetime.timedelta``.
    :raises ValueError: If format is invalid or empty.
    """
    compact = "".join(value.split()).lower()
    if not compact:
        raise ValueError("time cannot be empty")

    total_seconds = 0
    position = 0
    matched = False
    for match in _DURATION_RE.finditer(compact):
        if match.start() != position:
            raise ValueError(f"Invalid time value: {value!r}")

        amount = int(match.group(1))
        unit = match.group(2)
        total_seconds += amount * _UNIT_SECONDS[unit]
        position = match.end()
        matched = True

    if not matched or position != len(compact):
        raise ValueError(f"Invalid time value: {value!r}")

    return datetime.timedelta(seconds=total_seconds)
