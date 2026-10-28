from __future__ import annotations

from datetime import date as DateType
from datetime import datetime, timedelta
from typing import Generator, overload

from ..functions.day_type import day_type
from ..utils.time import hhmm2min, min2hhmm

SimulationDatetimeType = datetime | str | int | DateType | None

__all__ = ["SimulationDatetime", "SimulationInterval", "SimulationDatetimeType"]


class SimulationDatetime:
    def __init__(
        self,
        date: SimulationDatetimeType | SimulationDatetime = None,
        base_date: SimulationDatetimeType | SimulationDatetime = None,
        date_format: list[str] | str = ["%Y-%m-%d %H:%M:%S", "%H:%M", "%Y-%m-%d", "%Y-%m-%d %H:%M"],
    ):
        self._base_date = SimulationDatetime(base_date) if base_date is not None else None
        if date is None:
            self._dt = datetime.now()
        elif isinstance(date, str):
            if isinstance(date_format, str):
                date_format = [date_format]
            for fmt in date_format:
                try:
                    self._dt = datetime.strptime(date, fmt)
                    break
                except ValueError:
                    continue
        elif isinstance(date, (int, float)):
            self._dt = datetime(year=1970, month=1, day=1) + timedelta(minutes=date)
            # ridefinisco la data ma riducendola di 70 anni per riportarla al 1900
            self._dt = self._dt.replace(year=self._dt.year - 70)
        elif isinstance(date, SimulationDatetime):
            self._dt = date.dt
        elif isinstance(date, datetime):
            self._dt = date
        elif isinstance(date, DateType):
            self._dt = datetime(year=date.year, month=date.month, day=date.day)
        else:
            raise ValueError("Invalid type for simulation_date")
        self._dt = self._dt.replace(second=0, microsecond=0)
        if self._dt.year <= 1900 and self._base_date is not None:
            diff = self._dt.date() - datetime(1900, 1, 1).date()
            self._dt = (
                self._dt.replace(
                    year=self._base_date.dt.year, month=self._base_date.dt.month, day=self._base_date.dt.day
                )
                + diff
            )

    def copy(self) -> SimulationDatetime:
        return SimulationDatetime(self._dt)

    @classmethod
    def min2hhmm(cls, minutes: int) -> str:
        return min2hhmm(minutes)

    @classmethod
    def hhmm2min(cls, hhmm: str) -> int:
        return hhmm2min(hhmm)

    def combine(self, other: SimulationDatetime) -> SimulationDatetime:
        return SimulationDatetime(datetime.combine(self.date, other.dt.time()).replace(second=0, microsecond=0))

    def strftime(self, fmt: str) -> str:
        return self._dt.strftime(fmt)

    def replace(self, **kwargs) -> SimulationDatetime:
        return SimulationDatetime(self._dt.replace(**kwargs))

    @property
    def dt(self) -> datetime:
        return self._dt

    @property
    def date(self) -> DateType:
        return self._dt.date()

    def minutes_from_midnight(self, base_time: datetime | SimulationDatetime | None = None) -> int:
        if base_time is None:
            base_time = self._dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            if isinstance(base_time, SimulationDatetime):
                base_time = base_time.dt.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                base_time = base_time.replace(hour=0, minute=0, second=0, microsecond=0)
        delta: timedelta = self._dt - base_time
        return int(delta.total_seconds() // 60)

    def from_minutes(self, minutes: int, inplace: bool = False) -> SimulationDatetime:
        if inplace:
            self._dt = self._dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)
            return self
        else:
            return SimulationDatetime(
                self._dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)
            )

    @overload
    def subtract(
        self,
        other: timedelta | None = None,
        days: float = 0,
        minutes: float = 0,
        seconds: float = 0,
        microseconds: float = 0,
        weeks: float = 0,
        hours: float = 0.0,
    ) -> SimulationDatetime: ...
    @overload
    def subtract(self, other: SimulationDatetime) -> timedelta: ...

    def subtract(
        self,
        other: timedelta | SimulationDatetime | None = None,
        days: float = 0,
        minutes: float = 0,
        seconds: float = 0,
        microseconds: float = 0,
        weeks: float = 0,
        hours: float = 0.0,
    ) -> SimulationDatetime | timedelta:
        if other is None:
            other = timedelta()
        if isinstance(other, timedelta):
            other = other + timedelta(
                days=days, minutes=minutes, seconds=seconds, microseconds=microseconds, weeks=weeks, hours=hours
            )
            return SimulationDatetime(self._dt - other)
        elif isinstance(other, SimulationDatetime):
            return self._dt - other._dt
        else:
            raise TypeError("Unsupported type for subtraction")

    def add(
        self,
        other: timedelta | None = None,
        days: float = 0,
        minutes: float = 0,
        seconds: float = 0,
        microseconds: float = 0,
        weeks: float = 0,
        hours: float = 0.0,
    ) -> SimulationDatetime:
        if other is None:
            other = timedelta()
        other = other + timedelta(
            days=days, minutes=minutes, seconds=seconds, microseconds=microseconds, weeks=weeks, hours=hours
        )
        return SimulationDatetime(self._dt + other)

    @property
    def day_type(self) -> str:
        return day_type(self._dt)

    def __eq__(self, other) -> bool:
        return self._dt == SimulationDatetime(other)._dt

    def __ne__(self, other) -> bool:
        return self._dt != SimulationDatetime(other)._dt

    def __lt__(self, other) -> bool:
        return self._dt < SimulationDatetime(other)._dt

    def __le__(self, other) -> bool:
        return self._dt <= SimulationDatetime(other)._dt

    def __gt__(self, other) -> bool:
        return self._dt > SimulationDatetime(other)._dt

    def __ge__(self, other) -> bool:
        return self._dt >= SimulationDatetime(other)._dt

    def __str__(self) -> str:
        return f"{self._dt.strftime('%Y-%m-%d %H:%M')}"


class SimulationInterval:
    def __init__(
        self,
        start: SimulationDatetimeType | SimulationDatetime,
        end: SimulationDatetimeType | SimulationDatetime,
        simulation_date: SimulationDatetimeType | SimulationDatetime = None,
    ):

        self.__start: SimulationDatetime = SimulationDatetime(start)
        self.__end: SimulationDatetime = SimulationDatetime(end)
        self.__simulation_date: SimulationDatetime
        if self.__start.date.year <= 1900:
            self.__simulation_date = SimulationDatetime(simulation_date)
            self.__start = self.__start.combine(self.__simulation_date)
        else:
            simulation_date_start = SimulationDatetime(
                self.__start.dt.replace(hour=0, minute=0, second=0, microsecond=0)
            )
            if simulation_date is not None:
                simulation_date_or = SimulationDatetime(simulation_date)
                self.__simulation_date = simulation_date_or
            else:
                self.__simulation_date = simulation_date_start
        if self.__end.date.year <= 1900:
            self.__end = self.__end.combine(self.__simulation_date)
        if self.__start > self.__end:
            delta = self.__start.subtract(self.__end)
            self.__end = self.__end.add(timedelta(days=delta.days + 1))
        self.__duration = self.__end.subtract(self.__start)
        self.__time_slice = int(self.__duration.total_seconds() // 60)
        self.__time_start = self.__start.minutes_from_midnight(self.__start)
        self.__time_end = self.__end.minutes_from_midnight(self.__start)

    @property
    def time_start(self) -> int:
        """Returns the start time of the simulation interval in minutes from midnight."""
        return self.__time_start

    @property
    def time_end(self) -> int:
        """Returns the end time of the simulation interval in minutes from midnight."""
        return self.__time_end

    @property
    def start(self) -> SimulationDatetime:
        """Returns the start datetime of the simulation interval."""
        return self.__start

    @property
    def end(self) -> SimulationDatetime:
        """Returns the end datetime of the simulation interval."""
        return self.__end

    @property
    def simulation_date(self) -> SimulationDatetime:
        """Returns the simulation date associated with the simulation interval."""
        return self.__simulation_date

    @property
    def duration(self) -> timedelta:
        """Returns the duration of the simulation interval as a timedelta object."""
        return self.__duration

    @property
    def time_slice(self) -> int:
        """Returns the duration of the simulation interval in minutes."""
        return self.__time_slice

    def get_intervals(self, time_slice: int) -> Generator[SimulationInterval, None, None]:
        """Generates sub-intervals of the simulation interval with the specified time slice in minutes."""
        current_start = self.start
        while current_start < self.end:
            current_end = current_start.add(timedelta(minutes=time_slice))
            if current_end > self.end:
                current_end = self.end
            yield SimulationInterval(current_start, current_end, self.simulation_date)
            current_start = current_end

    def get_day_intervals(self) -> list[SimulationInterval]:
        """Returns the list of daily intervals contained within this simulation interval.
        Each daily interval starts at midnight and ends at 23:59 of the same day.
        The first day starts from the start time of the interval,
        while the last day ends at the end time of the interval.
        """
        intervals: list[SimulationInterval] = []
        current_start = self.start
        while current_start.date <= self.end.date:
            current_end = SimulationDatetime(
                datetime.combine(current_start.date, datetime.max.time()).replace(second=0, microsecond=0)
            )
            if current_end > self.end:
                current_end = self.end
            intervals.append(SimulationInterval(current_start, current_end, self.simulation_date))
            current_start = SimulationDatetime(
                datetime.combine(current_start.date + timedelta(days=1), datetime.min.time()).replace(
                    second=0, microsecond=0
                )
            )
        return intervals

    def __str__(self) -> str:
        """Returns a string representation of the simulation interval, including start, end, and duration in minutes."""
        return f"{self.start}-{self.end} ({self.__time_slice})"

    def __eq__(self, value):
        if not isinstance(value, SimulationInterval):
            return False
        return (
            self.__start == value.__start
            and self.__end == value.__end
            and self.__simulation_date == value.__simulation_date
            and self.__duration == value.__duration
            and self.__time_slice == value.__time_slice
        )

    def __ne__(self, value):
        return not self.__eq__(value)

    def __gt__(self, value):
        if not isinstance(value, SimulationInterval):
            return False
        return self.__start > value.__start

    def __lt__(self, value):
        if not isinstance(value, SimulationInterval):
            return False
        return self.__start < value.__start

    def __ge__(self, value):
        if not isinstance(value, SimulationInterval):
            return False
        return self.__start >= value.__start

    def __le__(self, value):
        if not isinstance(value, SimulationInterval):
            return False
        return self.__start <= value.__start
