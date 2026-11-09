from collections.abc import Callable
from operator import index

from shapely.geometry import LineString, MultiLineString


def make_inside_checker(
    time_start: int | None = None, time_end: int | None = None, normalize_at: int = 1440
) -> Callable[[int], bool]:
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

        expression = f"{start} <= t % {n} < {end}" if start < end else f"not ({end} <= t % {n} < {start})"

    # Compilazione eseguita soltanto durante la creazione.
    # Nella stringa vengono inseriti esclusivamente interi validati.
    return eval(f"lambda t: {expression}", {"__builtins__": {}})


def time_index(t0: float, delta_t: float, n_intervals: int, time_value: float) -> int:
    # Internal helper: time index.
    """Internal helper: time index."""
    if n_intervals <= 0:
        return 0
    return int(max(0, min(int((time_value - t0) // delta_t), n_intervals - 1)))


def multiline_to_line(multi_line: MultiLineString | LineString | None, get_first: bool = False) -> LineString | None:
    if multi_line is None:
        return None
    if isinstance(multi_line, LineString):
        return multi_line
    if not isinstance(multi_line, MultiLineString):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError(f"Expected MultiLineString, got {type(multi_line)}")

    if get_first:
        if len(multi_line.geoms) == 0:
            return LineString()
        return multi_line.geoms[0]

    # Extract all coordinates from the MultiLineString
    all_coords: list[tuple[float, ...]] = []

    for line in multi_line.geoms:
        all_coords.extend(line.coords)

    # Create a new LineString with the concatenated coordinates
    return LineString(all_coords)
