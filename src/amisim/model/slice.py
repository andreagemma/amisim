from __future__ import annotations

from datetime import timedelta

from graph import time_index

from .simulation_interval import SimulationDatetime, SimulationDatetimeType, SimulationInterval


class Slice:
    def __init__(
        self,
        simulation_date: SimulationDatetimeType | SimulationDatetime | None = None,
        start: SimulationDatetimeType | SimulationDatetime | None = None,
        end: SimulationDatetimeType | SimulationDatetime | None = None,
        time_slice: int | None = None,
        delta_t: int | None = None,
        pre_load: int = 0,
        post_load: int = 0,
    ):
        if simulation_date is not None:
            simulation_date = SimulationDatetime(simulation_date).replace(hour=0, minute=0, second=0, microsecond=0)
        if start is not None:
            start = SimulationDatetime(start, base_date=simulation_date)
        if end is not None:
            end = SimulationDatetime(end, base_date=simulation_date)
        if time_slice is None:
            if start is not None and end is not None:
                start = start.add(timedelta(minutes=-pre_load))
                end = end.add(timedelta(minutes=post_load))
                time_slice = int(end.subtract(start).total_seconds() // 60)
            else:
                time_slice = None
        if start is None:
            if end is not None and time_slice is not None:
                end = end.add(timedelta(minutes=post_load))
                start = end.add(timedelta(minutes=-time_slice))
                start = start.add(timedelta(minutes=-pre_load))
                time_slice = int(end.subtract(start).total_seconds() // 60)
            else:
                start = None
        if end is None:
            if start is not None and time_slice is not None:
                start = start.add(timedelta(minutes=-pre_load))
                end = start.add(timedelta(minutes=time_slice))
                end = end.add(timedelta(minutes=post_load))
                time_slice = int(end.subtract(start).total_seconds() // 60)
            else:
                end = None
        if start is None or end is None or time_slice is None:
            raise ValueError("Insufficient information to determine start, end, and time_slice")
        if start is None:
            raise ValueError("start must be determined before setting attributes")
        if end is None:
            raise ValueError("end must be determined before setting attributes")
        if time_slice is None:
            raise ValueError("time_slice must be determined before setting attributes")
        else:
            time_slice = int(time_slice)
        if end <= start:
            raise ValueError("end must be greater than start")
        if time_slice <= 0:
            raise ValueError("time_slice must be a positive integer")
        if time_slice != int(end.subtract(start).total_seconds() // 60):
            raise ValueError("time_slice must be equal to end - start")
        if delta_t is None:
            raise ValueError("delta_t must be provided")
        if time_slice % delta_t != 0:
            raise ValueError(f"time_slice must be a multiple of delta_t: {time_slice} % {delta_t} != 0")
        if simulation_date is None:
            simulation_date = SimulationDatetime(start)
        self._delta_t = delta_t
        self._time_start = start.minutes_from_midnight(simulation_date.dt)
        while self._time_start < 0:
            simulation_date = simulation_date.add(timedelta(days=-1))
            self._time_start = start.minutes_from_midnight(simulation_date.dt)
        self._time_end = end.minutes_from_midnight(simulation_date.dt)
        self._time_slice = time_slice
        self._start = start
        self._end = end
        intervals_range = range(self._time_start, self._time_end, self._time_slice)
        self._intervals = [(x, max(self._time_end, x + self._time_slice)) for x in intervals_range]
        self._num_intervals = len(self._intervals)
        self._simulation_interval = SimulationInterval(
            start=self._start, end=self._end, simulation_date=simulation_date
        )
        self.timestamp_to_id, self.timestamp_from_id = self._timestamp_to_id()
        self._pre_load = pre_load
        self._post_load = post_load

    @property
    def pre_load(self) -> int:
        return self._pre_load

    @property
    def post_load(self) -> int:
        return self._post_load

    def trim(self) -> Slice:
        return Slice(
            simulation_date=self.results_start.date,
            start=self.results_start_time,
            end=self.results_end_time,
            delta_t=self.delta_t,
            pre_load=0,
            post_load=0,
        )

    def normalize(self) -> Slice:
        return Slice(
            simulation_date=self.start.date,
            start=self.start,
            end=self.end,
            delta_t=self.delta_t,
            pre_load=self._pre_load,
            post_load=self._post_load,
        )

    @property
    def results_start(self) -> SimulationDatetime:
        return self.start.add(timedelta(minutes=self._pre_load)) if self._pre_load is not None else self.start

    @property
    def results_end(self) -> SimulationDatetime:
        return self.end.add(timedelta(minutes=-self._post_load)) if self._post_load is not None else self.end

    @property
    def results_start_time(self) -> int:
        return self.results_start.minutes_from_midnight(self.start.dt)

    @property
    def results_end_time(self) -> int:
        return self.results_end.minutes_from_midnight(self.start.dt)

    def _timestamp_to_id(self) -> tuple[dict, dict]:
        timestamp_to_id: dict | None = None
        for interval in self.simulation_interval.get_day_intervals():
            start = interval.start.minutes_from_midnight()
            end = interval.end.minutes_from_midnight()
            assert start <= end, "Start time must be less than or equal to end time"
            t_timestamps = range(start, end + 1, self.delta_t)
            n_current_timestamp_to_replace = len(timestamp_to_id) if timestamp_to_id is not None else 0
            id_timestamps = range(n_current_timestamp_to_replace, n_current_timestamp_to_replace + len(t_timestamps))
            if timestamp_to_id is None:
                timestamp_to_id = {}
            timestamp_to_id.update(dict(zip(t_timestamps, id_timestamps)))
        if timestamp_to_id is None:
            timestamp_to_id = {}
        reverse_id_to_timestamp = {v: k for k, v in timestamp_to_id.items()}

        return timestamp_to_id, reverse_id_to_timestamp

    def start_index(self) -> int:
        return 0

    def end_index(self) -> int:
        return time_index(
            t0=self.time_start, delta_t=self.delta_t, n_intervals=self._num_intervals, time_value=self._time_end
        )

    def t_index(self, time_value: int) -> int:
        return time_index(
            t0=self.time_start, delta_t=self.delta_t, n_intervals=self._num_intervals, time_value=time_value
        )

    @property
    def time_start(self) -> int:
        return self._time_start

    @property
    def time_end(self) -> int:
        return self._time_end

    @property
    def time_slice(self) -> int:
        return self._time_slice

    @property
    def start(self) -> SimulationDatetime:
        return self._start

    @property
    def end(self) -> SimulationDatetime:
        return self._end

    @property
    def intervals(self) -> list[tuple[int, int]]:
        return self._intervals

    @property
    def num_intervals(self) -> int:
        return self._num_intervals

    @property
    def delta_t(self) -> int:
        return self._delta_t

    @property
    def simulation_interval(self) -> SimulationInterval:
        return self._simulation_interval

    def __str__(self) -> str:
        return (
            f"Slice(time_start={self._time_start} "
            + (f"({self.results_start_time})" if self.results_start_time != self._time_start else "")
            + f", time_end={self._time_end} "
            + (f"({self.results_end_time})" if self.results_end_time != self._time_end else "")
            + f", time_slice={self._time_slice}, "
            f"delta_t={self._delta_t}, num_intervals={self._num_intervals}, "
            f"start={self._start}, end={self._end})"
        )

    def __eq__(self, value):
        if not isinstance(value, Slice):
            return False
        return (
            self._time_start == value._time_start
            and self._time_end == value._time_end
            and self._time_slice == value._time_slice
            and self._delta_t == value._delta_t
            and self._num_intervals == value._num_intervals
            and self._start == value._start
            and self._end == value._end
            and self._intervals == value._intervals
            and self._simulation_interval == value._simulation_interval
        )

    def __ne__(self, value):
        return not self.__eq__(value)

    def __gt__(self, value):
        if not isinstance(value, Slice):
            return False
        return self._start > value._start

    def __lt__(self, value):
        if not isinstance(value, Slice):
            return False
        return self._start < value._start

    def __ge__(self, value):
        if not isinstance(value, Slice):
            return False
        return self._start >= value._start

    def __le__(self, value):
        if not isinstance(value, Slice):
            return False
        return self._start <= value._start
