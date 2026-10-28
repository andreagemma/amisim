"""Static method of successive averages (MSA) assignment algorithm."""

from __future__ import annotations

from typing import Any

from ..base.base_simulator import BaseSimulator
from ..model.graph_model import GraphBase
from ..model.matrices_model import MultiModalDynamicMatrix
from ..model.modes_model import ModesType
from ..model.paths_model import MultimodalPathsType
from ..model.slice import Slice
from .assignment_aon import AssignmentAON
from .shortest_path import ShortestPath

__all__ = [
    "AssignmentMSA",
]


class AssignmentMSA(AssignmentAON):
    """Assign the demand on the network using the static method of successive averages (MSA)."""

    def __init__(
        self,
        use_parallel: bool | None = None,
        n_workers: float | None = None,
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
            use_parallel=use_parallel, n_workers=n_workers, simulator=simulator, shortest_path=shortest_path, **kwargs
        )
        self.max_iterations: int
        self.max_relative_gap: float

    def init(
        self,
        graph: GraphBase | None = None,
        modes: ModesType | None = None,
        slice: Slice | None = None,
        matrix: MultiModalDynamicMatrix | None = None,
        centroids: list | None = None,
        preloaded_paths: MultimodalPathsType | None = None,
        update_last_costs: bool | None = None,
        max_iterations: int | None = None,
        max_relative_gap: float | None = None,
        max_k: int | None = None,
        **kwargs: Any,
    ) -> AssignmentMSA:
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
        self.max_k = max_k if max_k is not None else self.ini.ASSIGNMENT.MSA_K
        return self

    def update(
        self,
        graph: GraphBase | None = None,
        modes: ModesType | None = None,
        slice: Slice | None = None,
        matrix: MultiModalDynamicMatrix | None = None,
        centroids: list | None = None,
        preloaded_paths: MultimodalPathsType | None = None,
        update_last_costs: bool | None = None,
        max_iterations: int | None = None,
        max_relative_gap: float | None = None,
        max_k: int | None = None,
        **kwargs: Any,
    ) -> AssignmentMSA:
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
        if max_k is not None:
            self.max_k = max_k
        return self

    def run(self, **kwargs):
        """Initialize and run the static simulation over the given time window.

        Args:
            None
        """
        super().run(**kwargs)
        tic_assignment = self.log.tic()

        self.iterations.clear()
        for self.iteration in self.get_iterations():
            assert self.iteration.id is not None, "Iteration ID should not be None"
            tic_iteration = self.log.tic()
            self.iteration.name = f"Ite: {self.iteration.id + 1}/{self.max_iterations} - "

            if self.calc_paths:
                self.calculate_shortest_paths()
                self.k_calculated += 1
            if self.k_calculated >= self.max_k:
                self.calc_paths = False
            if self.iteration.id < self.max_k:
                self.log.info(f"Preloading (k={self.k_calculated})")
                for mode, mat in self.matrix.get_all_matrices():
                    mode_paths = self.paths.get_by_mode(mode)
                    if mode_paths is None:
                        self.log.warning(f"No paths available for mode '{mode}'")
                        continue
                    for (source, target, t_start, _), k_paths in mode_paths.all_kpaths():
                        if not (0 <= t_start < self.slice.time_slice):
                            continue
                        if (n_paths := len(k_paths)) == 0:
                            continue
                        if (t := k_paths[0].get("t")) is None:
                            continue
                        t = int(t) % 1440
                        demand = mat.get_od(timestamp=t, origin=source, destination=target) * self.modes.get(
                            mode, {}
                        ).get("eq_factor", 1)
                        for path in k_paths:
                            path["path_flow"] = demand / n_paths
                self.update_performance()
                self.calc_rgap()
                self.update_infos()
                self.log.info(f"{self.iteration.name}Iteration completed in {tic_iteration.toc()} seconds")
                continue

            # % MSA parte 1-1/k
            """
            Decurto 1-1/k di flusso per ogni vecchio percorso
            I nuovi percorsi aumenteranno di 1/k il proprio flusso
            """
            for mode, mat in self.matrix.get_all_matrices():
                mode_paths = self.paths.get_by_mode(mode)
                if mode_paths is None:
                    self.log.warning(f"No paths available for mode '{mode}'")
                    continue
                for (source, target, t_start, _), k_paths in mode_paths.all_kpaths():
                    if not (0 <= t_start < self.slice.time_slice):
                        continue

                    if (n_paths := len(k_paths)) == 0:
                        continue
                    if self.ini.ASSIGNMENT.MSA_K_BALANCING > 0:
                        k = max(self.iteration.id - n_paths, 0) + self.ini.ASSIGNMENT.MSA_K_BALANCING
                    else:
                        k = self.iteration.id + 1
                    best = None
                    for path in k_paths:
                        path["path_flow"] *= 1 - 1 / k
                        if best is None or path["tot_cost"] < best["tot_cost"]:
                            best = path
                    assert best is not None, "No best path found"
                    if (t := best.get("t")) is None:
                        continue
                    t = int(t) % 1440
                    demand = mat.get_od(timestamp=t, origin=source, destination=target) * self.modes.get(mode, {}).get(
                        "eq_factor", 1
                    )
                    best["path_flow"] += demand / k
            self.update_performance()
            self.calc_rgap()
            self.update_infos()

            self.log.info(f"{self.iteration.name}Iteration completed in {tic_iteration.toc()} seconds")
            if self.test_convergence():
                break
        self.log.info(f"{self.name} assignment completed in {tic_assignment.toc()} seconds")


__all__ = ["AssignmentMSA"]
