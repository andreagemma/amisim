"""Static method of successive averages (MSA) assignment algorithm."""

from __future__ import annotations

from typing import Any

from ..base.base_simulator import BaseSimulator
from ..database import Execution
from ..model.graph_model import GraphBase
from ..model.matrices_model import MultiModalDynamicMatrix
from ..model.modes_model import ModesType
from ..model.paths_model import MultimodalPathsType
from ..model.slice import Slice
from .assignment_aon import AssignmentAON
from .shortest_path import ShortestPath

__all__ = [
    "Simulation",
]


class Simulation(AssignmentAON):
    """Assign the demand on the network using the static method of successive averages (MSA)."""

    def __init__(
        self,
        use_parallel: bool = False,
        n_workers: float | None = None,
        execution: Execution | None = None,
        simulator: BaseSimulator | None = None,
        shortest_path: ShortestPath | None = None,
        **kwargs,
    ):
        """Build the algorithm and its static simulator.

        Args:
            use_parallel: If `True`, the algorithm will use parallel processing.
            n_workers: Number of workers to use if running in parallel.
            **kwargs: Extra arguments forwarded to the base class and simulator.
        """
        super().__init__(
            use_parallel=use_parallel,
            n_workers=n_workers,
            execution=execution,
            simulator=simulator,
            shortest_path=shortest_path,
            **kwargs,
        )
        self.update_last_costs: bool = True
        self.preloaded_paths: MultimodalPathsType | None = None

    def init(
        self,
        graph: GraphBase | None = None,
        modes: ModesType | None = None,
        slice: Slice | None = None,
        matrix: MultiModalDynamicMatrix | None = None,
        centroids: list | None = None,
        preloaded_paths: MultimodalPathsType | None = None,
        update_last_costs: bool | None = True,
        max_iterations: int | None = None,
        max_relative_gap: float | None = None,
        **kwargs: Any,
    ) -> Simulation:
        super().init(
            graph=graph,
            modes=modes,
            slice=slice,
            matrix=matrix,
            centroids=centroids,
            preloaded_paths=preloaded_paths,
            update_last_costs=update_last_costs,
            max_iterations=max_iterations,
            max_relative_gap=max_relative_gap,
            **kwargs,
        )
        return self

    def update(
        self,
        graph: GraphBase | None = None,
        modes: ModesType | None = None,
        slice: Slice | None = None,
        matrix: MultiModalDynamicMatrix | None = None,
        centroids: list | None = None,
        preloaded_paths: MultimodalPathsType | None = None,
        update_last_costs: bool | None = True,
        max_iterations: int | None = None,
        max_relative_gap: float | None = None,
        **kwargs: Any,
    ) -> Simulation:
        super().update(
            graph=graph,
            modes=modes,
            slice=slice,
            matrix=matrix,
            centroids=centroids,
            preloaded_paths=preloaded_paths,
            update_last_costs=update_last_costs,
            max_iterations=max_iterations,
            max_relative_gap=max_relative_gap,
            **kwargs,
        )
        if update_last_costs is not None:
            self.update_last_costs = update_last_costs
        return self

    def run(self, **kwargs):
        """Initialize and run the static simulation over the given time window.

        Args:
            None
        """
        try:
            tic = self.log.info("Running Simulation").tic()
            self.set_execution_start()
            calc_paths = True

            if self.preloaded_paths is not None:
                self.paths.clear(new_paths=self.preloaded_paths)
                calc_paths = False
            else:
                self.paths.clear()
            self.iteration = self.get_new_iteration()
            assert self.iteration.id is not None, "Iteration ID should not be None"
            self.iteration.name = "Simulation"

            if calc_paths:
                self.calculate_shortest_paths()
            n_steps = self.paths.n_paths()
            step = 0
            percentage = 0
            for _, (mode, mat) in enumerate(self.matrix.get_all_matrices()):
                self.log.info(f"Assigning demand for mode '{mode}'")
                mode_paths = self.paths.get_by_mode(mode)
                if mode_paths is None:
                    self.log.warning(f"No paths available for mode '{mode}'")
                    continue
                for (source, target, t_start, _), k_paths in mode_paths.all_kpaths():
                    step += len(k_paths)

                    if round(step / n_steps * 50) == percentage:
                        self.set_execution_progress(round(step / n_steps * 50), f"Analyzing {step}/{n_steps} paths")
                        percentage += 10
                    if not (0 <= t_start < self.slice.time_slice):
                        continue
                    if (n_paths := len(k_paths)) == 0:
                        continue
                    if (t := k_paths[0].get("t")) is None:
                        continue
                    t = int(t) % 1440
                    demand = mat.get_od(timestamp=t, origin=source, destination=target) * self.modes.get(mode, {}).get(
                        "eq_factor", 1
                    )
                    tot_flow = sum(path.get("path_flow", 0) for path in k_paths)
                    if tot_flow > 0:
                        for path in k_paths:
                            path["path_flow"] = path["path_flow"] / tot_flow * demand
                    else:
                        for path in k_paths:
                            path["path_flow"] = demand / n_paths
            self.set_execution_progress(50, "Analyzed all paths")
            self.update_performance()
            self.set_execution_progress(100, "Updated performance")
            self.log.info(f"Simulation completed in {tic.toc():.2f} seconds")
            self.set_execution_success()
        except Exception as e:
            self.log.error(f"Simulation failed: {e}")
            self.set_execution_failed(f"Simulation failed: {e}")


__all__ = ["Simulation"]
