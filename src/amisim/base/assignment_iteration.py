from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AssignmentIteration:
    id: int | None = None
    dt_start: datetime = field(default_factory=datetime.now)
    dt_end: datetime | None = None
    rgap: float | None = None
    current_travel_time: float = 0.0
    total_travel_time: float = 0.0
    total_demand: float = 0.0
    total_vehicles: int | None = None
    n_paths: int = 0
    n_unique_paths: int = 0
    k_paths: int = 0
    total_cpu_time: float = 0.0
    name: str | None = None

    def duration(self) -> float | None:
        if self.dt_end is not None:
            return (self.dt_end - self.dt_start).total_seconds()
        return None
