from __future__ import annotations

from typing import Any

from ..model.graph_model import GraphBase
from ..model.modes_model import ModesType
from ..model.paths_model import MultimodalPathsType
from .base_algorithm import BaseAlgorithm


class BaseSimulator(BaseAlgorithm):
    def __init__(self, use_parallel: bool | None = None, n_workers: float | None = None, **kwargs) -> None:
        """Build the simulator and resolve the parallel runtime to use.

        Args:
            use_parallel: If `True`, the simulator will use parallel processing.
            n_workers: Number of workers to use if running in parallel.
            **kwargs: Extra arguments forwarded to the base simulator.
        """
        super().__init__(**kwargs)
        self.paths: MultimodalPathsType
        self.use_parallel: bool = use_parallel if use_parallel is not None else True
        self.n_workers: float | None = n_workers if n_workers is not None else self.app.ini.ASSIGNMENT.NUM_CPUS
        self.graph: GraphBase
        self.time_start: int
        self.time_end: int
        self.modes: ModesType

    def init(
        self,
        graph: GraphBase | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        paths: MultimodalPathsType | None = None,
        modes: ModesType | None = None,
        **kwargs: Any,
    ) -> BaseSimulator:
        self.graph = graph if graph is not None else self.app.workspace.graph_model.graph
        self.time_start = time_start if time_start is not None else self.graph.tstart
        self.time_end = time_end if time_end is not None else self.graph.tend
        if modes is not None:
            self.modes = modes
        if not hasattr(self, "modes") or (self.modes is None and "modes" in self.graph):
            self.modes = self.graph["modes"]
        if not hasattr(self, "modes") or self.modes is None:
            self.modes = self.app.workspace.modes_model.modes
            self.graph["modes"] = self.modes
        if paths is not None:
            self.paths = paths
        return self

    def update(
        self,
        graph: GraphBase | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        paths: MultimodalPathsType | None = None,
        modes: ModesType | None = None,
        **kwargs: Any,
    ) -> BaseSimulator:
        self.graph = graph or self.graph
        self.time_start = time_start if time_start is not None else self.time_start
        self.time_end = time_end if time_end is not None else self.time_end
        if modes is not None:
            self.modes = modes
        if paths is not None:
            self.paths = paths
        return self

    def run(self, **kwargs):
        pass

    def save_state(self, **kwargs: Any):
        pass
