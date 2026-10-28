"""Time parsing helpers used by retention and cleanup workflows."""

from __future__ import annotations

import bisect
import datetime
import re
from operator import index

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

    Args:
        value: Duration expression, e.g. ``"2d"``.

    Returns:
        Parsed duration as ``datetime.timedelta``.

    Raises:
        ValueError: If format is invalid or empty.
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


def min2hhmm(minutes: int) -> str:
    """Return the minutes `minutes` formatted as `HH:MM`."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def hhmm2min(hhmm: str) -> int:
    """Return the `HH:MM` string converted to minutes."""
    hours, mins = map(int, hhmm.split(":"))
    return hours * 60 + mins


def get_intersecting_intervals(int_list: list[int], time_start: int, time_end: int):
    # Trova il primo intervallo che termina dopo time_start
    # bisect_right trova l'indice del primo elemento strettamente maggiore di time_start
    start_idx = bisect.bisect_right(int_list, time_start)
    # Se il primo valore in assoluto è > time_start, partiamo comunque dall'indice 0
    start_idx = max(0, start_idx - 1)

    # Trova l'ultimo intervallo che inizia prima di time_end
    # bisect_left trova dove inserire time_end mantenendo l'ordine (escludendo time_end stesso)
    end_idx = bisect.bisect_left(int_list, time_end)

    # Restituisce la fetta della lista originale che interseca la slice
    return int_list[start_idx:end_idx]


def is_inside_interval(x: int, lower: int | None = None, upper: int | None = None, normalize_at=1440) -> bool:
    if lower is None:
        return upper is None or x % normalize_at < upper % normalize_at

    if upper is None:
        return x % normalize_at >= lower % normalize_at

    if upper - lower >= normalize_at:
        return True

    t_norm = x % normalize_at
    start = lower % normalize_at
    end = upper % normalize_at

    if start < end:
        return t_norm >= start and t_norm < end

    return t_norm >= start or t_norm < end


def make_inside_checker(time_start=None, time_end=None, normalize_at=1440):
    # Accetta interi e oggetti compatibili con __index__.
    n = index(normalize_at)
    if n <= 0:
        raise ValueError("normalize_at deve essere positivo")

    start = None if time_start is None else index(time_start)
    end = None if time_end is None else index(time_end)

    if start is None:
        if end is None:
            return lambda t: True

        expression = f"t % {n} < {end % n}"

    elif end is None:
        expression = f"t % {n} >= {start % n}"

    elif end - start >= n:
        return lambda t: True

    else:
        start %= n
        end %= n

        if start == end:
            return lambda t: True

        if start < end:
            expression = f"{start} <= t % {n} < {end}"
        else:
            expression = f"not ({end} <= t % {n} < {start})"

    # Compilazione eseguita soltanto durante la creazione.
    # Nella stringa vengono inseriti esclusivamente interi validati.
    return eval(f"lambda t: {expression}", {"__builtins__": {}})
