"""Static all-or-nothing assignment algorithm."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Literal

import geopandas as gpd
import numpy as np
import pandas as pd

from ..base.base_algorithm import BaseAlgorithm
from ..base.base_loader import BaseLoader, OutputType
from ..base.base_simulator import BaseSimulator
from ..database import Execution
from ..model.graph_model import GraphBase, GraphModel
from ..model.matrices_model import MultiModalDynamicMatrix
from ..model.matrix_ass import MatrixAss
from ..model.modes_model import ModesType
from ..model.paths_model import MultimodalPathsType, PathsModel
from ..model.slice import Slice
from ..simulators.static_simulator import StaticSimulator
from .shortest_path import ShortestPath

__all__ = ["AssignmentAON", "Iteration"]


@dataclass
class Iteration:
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


class AssignmentAON(BaseAlgorithm):
    """Assign the demand on the network with a static all-or-nothing loading."""

    def __init__(
        self,
        use_parallel: bool | None = None,
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
        super().__init__(execution=execution, **kwargs)
        self.use_parallel: bool = use_parallel if use_parallel is not None else True
        self.n_workers: float | None = n_workers if n_workers is not None else self.app.ini.ASSIGNMENT.NUM_CPUS
        self.simulator = (
            simulator
            if simulator is not None
            else StaticSimulator(use_parallel=self.use_parallel, n_workers=self.n_workers, **kwargs)
        )
        self.paths: MultimodalPathsType = MultimodalPathsType()
        self.graph: GraphBase
        self.modes: ModesType
        self.shortest_path: ShortestPath = (
            shortest_path if shortest_path is not None else ShortestPath(app=self.app, use_parallel=self.use_parallel)
        )
        self.slice: Slice
        self.matrix: MultiModalDynamicMatrix
        self.matrix_assignment: MatrixAss | None = None
        self.centroids: list
        self.iteration: Iteration = Iteration(id=-1)
        self.iteration.name = ""
        self.iterations: list[Iteration] = []
        self.total_travel_time: float = 0.0
        self.preloaded_paths: MultimodalPathsType | None = None
        self.max_iterations: int
        self.max_relative_gap: float
        self.calc_paths: bool = True
        self.k_calculated: int = 0
        self.name: str = self.__class__.__name__
        self._agg_results: gpd.GeoDataFrame | None = None
        self._trace_results: gpd.GeoDataFrame | None = None
        self._signalized_results: gpd.DataFrame | None = None
        self._stats_results: pd.DataFrame | None = None

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
    ) -> AssignmentAON:
        if graph is not None:
            self.graph = graph
        if slice is not None:
            self.slice = slice
        if modes is not None:
            self.modes = modes
        if matrix is not None:
            self.matrix = matrix
        if centroids is not None:
            self.centroids = centroids
        if preloaded_paths is not None:
            self.preloaded_paths = preloaded_paths
        if self.preloaded_paths is None and self.app.workspace.has_preloaded_paths:
            self.preloaded_paths = self.app.workspace.preloaded_paths_model.paths
        self.update_last_costs: bool = False if update_last_costs is None else update_last_costs
        self.max_iterations = max_iterations if max_iterations is not None else self.ini.ASSIGNMENT.MSA_MAX_ITE
        self.max_relative_gap = max_relative_gap if max_relative_gap is not None else self.ini.ASSIGNMENT.MSA_RGAP

        if not hasattr(self, "graph"):
            assert self.app.workspace.graph_model is not None, "Workspace not found in app"
            assert self.app.workspace.graph_model.graph is not None, "Graph not found in workspace"
            self.graph = self.app.workspace.graph_model.graph
        if not hasattr(self, "modes"):
            if "modes" in self.graph:
                self.modes = self.graph["modes"]
            else:
                assert self.app.workspace.modes_model is not None, "Workspace not found in app"
                assert self.app.workspace.modes_model.modes is not None, "Modes not found in workspace"
                self.modes = self.app.workspace.modes_model.modes
                self.graph["modes"] = self.modes
        if not hasattr(self, "slice"):
            assert self.app.workspace.simulation_slice is not None, "Slice not found in workspace"
            self.slice = self.app.workspace.simulation_slice
        if not hasattr(self, "matrix"):
            assert self.app.workspace.matrices_model is not None, "Workspace not found in app"
            assert self.app.workspace.matrices_model.matrix is not None, "Matrix not found in workspace"
            self.matrix = self.app.workspace.matrices_model.matrix
        if not hasattr(self, "centroids"):
            if "centroids" in self.graph:
                self.centroids = self.graph["centroids"]
            else:
                assert self.app.workspace.graph_model is not None, "Workspace not found in app"
                assert self.app.workspace.graph_model.centroids is not None, "Centroids not found in workspace"
                self.centroids = self.app.workspace.graph_model.centroids
                self.graph["centroids"] = self.centroids

        self.shortest_path = self.shortest_path.init(
            graph=self.graph,
            modes=self.modes,
            slice=self.slice,
            matrix=self.matrix,
            centroids=self.centroids,
            **kwargs,
        )
        self.simulator = self.simulator.init(
            graph=self.graph,
            modes=self.modes,
            slice=self.slice,
            matrix=self.matrix,
            centroids=self.centroids,
            **kwargs,
        )
        self.total_travel_time = 0.0
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
        **kwargs: Any,
    ) -> AssignmentAON:
        if graph is not None:
            self.graph = graph
        if slice is not None:
            self.slice = slice
        if modes is not None:
            self.modes = modes
        if matrix is not None:
            self.matrix = matrix
        if centroids is not None:
            self.centroids = centroids
        if preloaded_paths is not None:
            self.preloaded_paths = preloaded_paths
        if update_last_costs is not None:
            self.update_last_costs = update_last_costs
        if max_iterations is not None:
            self.max_iterations = max_iterations
        if max_relative_gap is not None:
            self.max_relative_gap = max_relative_gap

        if not hasattr(self, "graph"):
            assert self.app.workspace.graph_model is not None, "Workspace not found in app"
            assert self.app.workspace.graph_model.graph is not None, "Graph not found in workspace"
            self.graph = self.app.workspace.graph_model.graph
        if not hasattr(self, "modes"):
            assert self.app.workspace.modes_model is not None, "Workspace not found in app"
            assert self.app.workspace.modes_model.modes is not None, "Modes not found in workspace"
            self.modes = self.app.workspace.modes_model.modes
        if not hasattr(self, "slice"):
            assert self.app.workspace.simulation_slice is not None, "Slice not found in workspace"
            self.slice = self.app.workspace.simulation_slice
        if not hasattr(self, "matrix"):
            assert self.app.workspace.matrices_model is not None, "Workspace not found in app"
            assert self.app.workspace.matrices_model.matrix is not None, "Matrix not found in workspace"
            self.matrix = self.app.workspace.matrices_model.matrix
        if not hasattr(self, "centroids"):
            assert self.app.workspace.graph_model is not None, "Workspace not found in app"
            assert self.app.workspace.graph_model.centroids is not None, "Centroids not found in workspace"
            self.centroids = self.app.workspace.graph_model.centroids
        self.simulator = self.simulator.update(
            graph=self.graph,
            modes=self.modes,
            slice=self.slice,
            matrix=self.matrix,
            centroids=self.centroids,
            **kwargs,
        )
        self.shortest_path = self.shortest_path.update(
            graph=self.graph,
            modes=self.modes,
            slice=self.slice,
            matrix=self.matrix,
            centroids=self.centroids,
            **kwargs,
        )
        self.paths = MultimodalPathsType()
        self.total_travel_time = 0.0
        return self

    def calculate_shortest_paths(self):
        tic = self.log.debug("Calculating shortest paths...").tic()
        paths = self.shortest_path.run(
            graph=self.graph,
            nodes=self.centroids,
            modes=self.modes,
            timestamps=list(np.arange(0, self.slice.time_slice, self.graph.delta_t).round().astype(int).tolist()),
        )
        self.log.debug(f"{paths.n_paths()} paths calculated in %.2f seconds" % self.log.toc()).tic()
        if paths is None:
            raise RuntimeError("Failed to compute shortest paths")
        if self.paths is None:
            self.paths = paths.paths
        else:
            self.paths.merge(paths.paths)
        self.log.debug("Paths set updated in %.2f seconds" % self.log.toc())
        self.log.info("Paths updated in %.2f seconds" % tic.toc()).tic()
        self.log.info(f"Total paths calculated: {paths.n_paths()} - unique: {paths.n_unique_paths()}")

    def get_new_iteration(self) -> Iteration:
        self.iteration = Iteration(id=len(self.iterations))
        self.iteration.name = f"Ite: {self.iteration.id}"
        self.iterations.append(self.iteration)
        return self.iteration

    def get_iterations(self) -> Generator[Iteration, None, None]:
        self.iterations.clear()
        for i in range(0, self.max_iterations):
            self.get_new_iteration()
            yield self.iteration

    def run(self, **kwargs):
        """Initialize and run the static simulation over the given time window.

        Args:
            None
        """
        if self.simulator:
            self.name = f"{self.__class__.__name__} ({self.simulator.__class__.__name__})"
        tic = self.log.info(f"Running {self.name}...").tic()

        modes_ws = set(self.modes.keys())
        modes_mat = set(self.matrix.modes)
        modes_in_ws_no_mat = modes_ws - modes_mat
        modes_in_mat_no_ws = modes_mat - modes_ws
        if modes_ws != modes_mat:
            if len(modes_in_ws_no_mat) > 0:
                self.log.warning(
                    f"The modes {modes_in_ws_no_mat} in the workspace are not present in the matrices. Retaining only the matrix modes. {modes_ws & modes_mat} "
                )
                for m in modes_in_ws_no_mat:
                    self.modes.pop(m)
            if len(modes_in_mat_no_ws) > 0:
                self.log.warning(
                    f"The modes {modes_in_mat_no_ws} in the matrices are not present in the workspace. Retaining only the workspace modes. {modes_ws & modes_mat} "
                )
                for m in modes_in_mat_no_ws:
                    self.matrix.pop(m)
        if self.preloaded_paths is not None:
            self.paths.clear(new_paths=self.preloaded_paths)
            self.calc_paths = False
            self.k_calculated = self.paths.k_paths()
        else:
            self.paths.clear()
            self.calc_paths = True
            self.k_calculated = 0

        if self.__class__ != AssignmentAON:
            self.iterations.clear()
            return

        if self.calc_paths:
            self.calculate_shortest_paths()
        self.log.debug("Loading of demand to best paths...")
        for mode, mat in self.matrix.get_all_matrices():
            mode_paths = self.paths.get_by_mode(mode)
            if mode_paths is None:
                self.log.warning(f"No paths available for mode '{mode}'")
                continue
            for (source, target, t_start, _), k_paths in mode_paths.all_kpaths():
                if not (0 <= t_start < self.slice.time_slice):
                    continue
                n_paths = len(k_paths)
                if n_paths == 0:
                    continue
                t = k_paths[0].get("t")
                if t is None:
                    continue
                t = int(t) % 1440
                demand = mat.get_od(timestamp=t % 1440, origin=source, destination=target) * self.modes.get(
                    mode, {}
                ).get("eq_factor", 1)
                for path in k_paths:
                    assert t == int(path.get("t", 0.0))
                    path["path_flow"] = demand / n_paths

        self.simulator.init(time_start=self.slice.time_start, time_end=self.slice.time_end)
        self.simulator.update(paths=self.paths)
        self.simulator.run(time_start=self.slice.time_start, time_end=self.slice.time_end)
        self.update_infos()
        self.log.info(f"{self.name} run completed in %.2f seconds" % tic.toc())

    def update_infos(self):
        self.iteration.n_paths = self.paths.n_paths()
        self.iteration.n_unique_paths = self.paths.n_unique_paths()
        self.iteration.dt_end = datetime.now()
        self.iteration.total_demand = sum([path["path_flow"] for path in self.paths.all_paths()])
        self.total_travel_time = sum([path["tot_cost"] * path["path_flow"] for path in self.paths.all_paths()])
        self.iteration.total_travel_time = self.total_travel_time
        self.iteration.k_paths = self.paths.k_paths()
        if not self.iteration.current_travel_time:
            self.iteration.current_travel_time = self.total_travel_time
        if self.simulator and hasattr(self.simulator, "vehs"):
            if vehs := getattr(self.simulator, "vehs", None):
                self.iteration.total_vehicles = len(vehs)
        else:
            self.iteration.total_vehicles = None
        et = self.log.elapsed_time()
        self.iteration.total_cpu_time = et.total_seconds
        self.write_running_stats()

        self.log.info(f"{self.iteration.name}Total Flows: {self.iteration.total_demand}")
        self.log.info(f"{self.iteration.name}Last Veh*h: {self.iteration.current_travel_time / 60}")  # type: ignore
        self.log.info(f"{self.iteration.name}Total Veh*h: {self.total_travel_time / 60}")  # type: ignore
        self.log.info(f"{self.iteration.name}Total Paths: {self.iteration.n_paths}")
        self.log.info(f"{self.iteration.name}Unique Paths: {self.iteration.n_unique_paths}")
        self.log.info(f"{self.iteration.name}K-Paths: {self.iteration.k_paths}")

        if self.iteration.total_vehicles is not None:
            self.log.info(f"{self.iteration.name}Moving Vehicles: {self.iteration.total_vehicles}")

    def calc_rgap(self):
        if self.iteration.id is None or self.iteration.id <= 1:
            return None
        if self.iteration.id > 1 and self.paths:
            assert self.matrix is not None, "OD matrices must be loaded before calculating rgap"
            assert self.paths is not None, "Path sets must be loaded before calculating rgap"
            assert self.modes is not None, "Modes must be loaded before calculating rgap"
            self.iteration.current_travel_time = 0
            for mode, mat in self.matrix.get_all_matrices():
                mode_paths = self.paths.get_by_mode(mode)
                if mode_paths is None:
                    self.log.warning(f"No paths available for mode '{mode}'")
                    continue
                for (source, target, t_start, _), k_paths in mode_paths.all_kpaths():
                    if source == target:
                        continue
                    if (t := k_paths[0].get("t")) is None:
                        continue
                    t = int(t) % 1440
                    demand = mat.get_od(timestamp=t, origin=source, destination=target) * self.modes.get(mode, {}).get(
                        "eq_factor", 1
                    )
                    if demand > 0:
                        best = min(k_paths, key=lambda path: path["tot_cost"])
                        self.iteration.current_travel_time += demand * best["tot_cost"]

            if self.iteration.current_travel_time == 0:
                rgap = 0.0
            else:
                rgap = abs(self.total_travel_time - self.iteration.current_travel_time)
                rgap /= self.iteration.current_travel_time
            self.iteration.rgap = rgap
            self.log.info(f"{self.iteration.name}Relative Gap on paths times: {self.iteration.rgap}")

    def test_convergence(self):
        if self.iteration.id is None or self.iteration.id < 0:
            return False
        if self.iteration.id >= self.max_iterations:
            self.log.info(f"{self.iteration.name}Convergence reached for maximum iterations {self.max_iterations}")
            return True
        if self.iteration.rgap is None:
            return False
        if self.iteration.rgap < self.max_relative_gap:
            self.log.info(f"{self.iteration.name}Convergence reached with relative gap: {self.iteration.rgap}")
            return True
        else:
            self.log.info(f"{self.iteration.name}Convergence not reached, relative gap: {self.iteration.rgap}")
            return False

    def update_performance(self):
        tic = self.log.debug("Updating performance...").tic()

        self.graph.reset_links("flow", 0)
        for mode in self.modes:
            self.graph.reset_links(name=f"flow_{mode}", value=0)
        self.graph.reset_links("time", lambda link, i=None: link["t0"])

        self.log.debug("Graph resetted in %.2f seconds" % self.log.toc()).tic()

        update_costs = (self.iteration.id != self.max_iterations - 1) or self.update_last_costs
        # aggiorno i tempi nel grafo
        if self.simulator:
            self.simulator.update(paths=self.paths)
            self.simulator.run()
            self.update_costs(update_nodes=False, update_links=True, update_turns=False)
        else:
            if update_costs:
                self.update_costs(update_nodes=False, update_links=True, update_turns=False)
        self.log.info(f"{self.iteration.name}Performance updated in %.2f seconds" % tic.toc())

    def update_costs(self, update_nodes=True, update_links=True, update_turns=True):
        tic = self.log.debug("Updating costs...").tic()
        graph = self.graph
        turn_cost = self.shortest_path.turn_cost_field
        link_cost = self.shortest_path.link_cost_field
        node_cost = self.shortest_path.node_cost_field

        other_graph = self.simulator.graph

        for link in graph.get_all_links():
            idx = link["idx"]
            link[link_cost] = other_graph.get_link_or_error(idx)[link_cost]

        for path in self.paths.all_paths():
            if len(path["links"]) == 0:
                continue
            cost = 0.0
            prev_link = None
            costs = list(path.costs)
            for i, l_idx in enumerate(path.get_links()):
                # costs[i] = cost
                t = path["t"] + cost
                link = graph.get_link(l_idx)
                assert link is not None, f"Link with index {l_idx} not found in the graph."
                t_idx = graph.time_index(t)
                new_cost = 0.0
                if update_turns and i > 0 and prev_link is not None:
                    turn = graph.get_turn_by_links(prev_link["idx"], link["idx"])
                    if turn:
                        new_cost += turn[turn_cost][t_idx]
                if update_nodes:
                    if node_i := graph.get_node(link.get("i", None)):
                        new_cost += node_i[node_cost][t_idx]
                if update_links:
                    new_cost += link[link_cost][t_idx]
                prev_link = link
                cost += new_cost
                costs[i] = cost
            path["costs"] = tuple(costs)
            path["tot_cost"] = cost
        self.log.info("Costs updated in %.2f seconds" % tic.toc())

    def write_running_stats(self):
        try:
            if params := self.parser.get(self.ini.PARAMS.ALGORITHM_LOG):
                self.log.info("Saving stats...")
                df = pd.DataFrame([asdict(si) for si in self.iterations])
                if df is None or df.empty:
                    self.log.warning("No statistics to save")
                    return
                mode = None if len(df) == 1 else "append"
                BaseLoader.write(engine=self.engine, df=df, params=params, mode=mode)
        except Exception as e:
            self.log.error("Failed to save statistics:", exc_info=e, stack_info=True)

    def write_paths_results(
        self,
        params: OutputType | None = None,
        results: gpd.GeoDataFrame | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        on_no_data: str | Literal["ignore", "warn", "error"] = "warn",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ):
        try:
            df = (
                results
                if results is not None
                else self.get_paths_results(time_start=time_start, time_end=time_end, on_error=on_error)
            )

            if df is None or len(df) == 0:
                if on_no_data == "warn":
                    self.log.warning("No paths available to write")
                elif on_no_data == "error":
                    raise ValueError("No paths available to write")
                return
            else:
                if params is None:
                    params = self.parser.get(self.ini.PARAMS.PATHS_OUTPUT)
                BaseLoader.write(engine=self.engine, df=df, params=params)
        except Exception as e:
            if on_error == "error":
                raise
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while writing paths: {e}")

    def write_state_graph(self, destination: Path | str | None = None, slice: Slice | None = None) -> None:
        if destination is None:
            destination = Path(self.parser.get(self.ini.PARAMS.STATE))
        slice = slice or self.slice
        graph = self.graph.cut_time_slice(
            time_start=slice.results_start_time,
            time_end=slice.results_end_time,
            rebase=slice.results_start.minutes_from_midnight(),
            inplace=False,
        )
        assert graph is not None, "Graph should not be None after cutting the time slice."
        if graph.empty:
            self.log.warning("No nodes available in the graph after cutting the time slice.")
        else:
            GraphModel.write_state(graph=graph, destination=destination, slice=self.slice)

    def write_state_paths(self, destination: Path | str | None = None, slice: Slice | None = None) -> None:
        if destination is None:
            destination = Path(self.parser.get(self.ini.PARAMS.STATE))
        slice = slice or self.slice
        paths = self.paths.cut_time_slice(
            time_start=slice.results_start_time,
            time_end=slice.results_end_time,
            rebase=slice.results_start.minutes_from_midnight(),
            inplace=False,
        )
        assert paths is not None, "Paths should not be None after cutting the time slice."
        if paths.n_paths() == 0:
            self.log.warning("No paths available after cutting the time slice.")
        else:
            PathsModel.write_state(paths=paths, destination=destination, slice=self.slice)

    def get_paths_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ) -> gpd.GeoDataFrame | None:
        """Get paths for the specified mode, source, and target."""

        try:
            df: pd.DataFrame | gpd.GeoDataFrame | None = self.paths.to_pandas(
                G=self.graph, crs_link=self.ini.GENERAL.CRS_CALC
            )
            if df is None:
                return None
            if not isinstance(df, gpd.GeoDataFrame):
                raise ValueError("Expected a GeoDataFrame for paths")
            if "t" in df.columns and pd.api.types.is_numeric_dtype(df["t"]) and "time" not in df.columns:
                time_start, time_end = self.get_time_results(time_start=time_start, time_end=time_end)
                df = df.query(f"t >= {time_start} and t <= {time_end}")
                df["t_base"] = time_start
                df["t_start"] = df["t"] - df["t_base"]
                sd = self.slice.start.copy()
                time_series = pd.to_timedelta(df["t"], unit="m") + sd._dt.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                df.insert(0, "time", time_series)
            return df
        except Exception as e:
            if on_error == "error":
                raise
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while getting paths results: {e}")
            return None

    def get_time_results(self, time_start: int | None = None, time_end: int | None = None, **kwargs: Any):
        ret_start = time_start if time_start is not None else self.slice.results_start_time
        ret_end = time_end if time_end is not None else self.slice.results_end_time
        return ret_start, ret_end

    def get_agg_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        on_not_available: str | Literal["ignore", "warn", "error"] = "warn",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ) -> gpd.GeoDataFrame | None:
        self.log.tic()
        try:
            if self._agg_results is not None:
                return self._agg_results

            if not hasattr(self.simulator, "get_agg_results"):
                if on_not_available == "error":
                    raise ValueError("Aggregated results not available")
                elif on_not_available.startswith("warn"):
                    self.log.warning("Aggregated results not available")
                return None

            """Get aggregated simulation results for the given time window and aggregation interval."""
            time_start, time_end = self.get_time_results(time_start=time_start, time_end=time_end)
            ret = self.simulator.get_agg_results(time_start=time_start, time_end=time_end)
            if ret is None:
                return None
            self.log.info("Retrieved aggregated results in %.2f seconds" % self.log.toc()).tic()
            if "time" in ret.columns and pd.api.types.is_numeric_dtype(ret["time"]):
                sd = self.slice.start.copy()
                ret["time"] = pd.to_timedelta(ret["time"], unit="m") + sd._dt.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            self._agg_results = ret
        except Exception as e:
            if on_error == "error":
                self.log.error(f"Error while getting aggregated results: {e}")
                raise e
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while getting aggregated results: {e}")
            return None
        return ret

    def write_agg_results(
        self,
        params: OutputType | None = None,
        results: gpd.GeoDataFrame | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        on_not_available: str | Literal["ignore", "warn", "error"] = "warn",
        on_no_data: str | Literal["ignore", "warn", "error"] = "warn",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ):
        try:
            df = (
                results
                if results is not None
                else self.get_agg_results(time_start=time_start, time_end=time_end, on_not_available=on_not_available)
            )
            if df is None or len(df) == 0:
                if on_no_data == "error":
                    raise ValueError("No aggregated results available to write")
                elif on_no_data.startswith("warn"):
                    self.log.warning("No aggregated results available to write")
            else:
                if params is None:
                    params = self.parser.get(self.ini.PARAMS.FLOWS_OUTPUT)
                BaseLoader.write(engine=self.engine, df=df, params=params)
                self.log.info("Aggregated results written successfully")
        except Exception as e:
            if on_error == "error":
                self.log.error(f"Error while writing aggregated results: {e}")
                raise e
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while writing aggregated results: {e}")

    def get_stats_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        on_not_available: str | Literal["ignore", "warn", "error"] = "warn",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ) -> pd.DataFrame | None:
        self.log.tic()
        try:
            if self._stats_results is not None:
                return self._stats_results
            if hasattr(self.simulator, "get_stats_results"):
                ret = self.simulator.get_stats_results(time_start=time_start, time_end=time_end)
                self._stats_results = ret
                if ret is not None:
                    self.log.info("Retrieved statistical results in %.2f seconds" % self.log.toc())
                return ret
            else:
                if on_not_available == "error":
                    raise ValueError("Statistical results not available")
                elif on_not_available.startswith("warn"):
                    self.log.warning("Statistical results not available")
                return None
        except Exception as e:
            if on_error == "error":
                self.log.error(f"Error while getting statistical results: {e}")
                raise e
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while getting statistical results: {e}")
            return None

    def write_stats_results(
        self,
        params: OutputType | None = None,
        results: pd.DataFrame | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        on_not_available: str | Literal["ignore", "warn", "error"] = "ignore",
        on_no_data: str | Literal["ignore", "warn", "error"] = "warn",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ):
        try:
            df = (
                results
                if results is not None
                else self.get_stats_results(
                    time_start=time_start, time_end=time_end, on_not_available=on_not_available, on_error=on_error
                )
            )
            if df is None or len(df) == 0:
                if on_no_data == "error":
                    raise ValueError("No statistical results available to write")
                elif on_no_data.startswith("warn"):
                    self.log.warning("No statistical results available to write")
                    return
            else:
                if params is None:
                    params = self.parser.get(self.ini.PARAMS.STATS_OUTPUT)
                BaseLoader.write(engine=self.engine, df=df, params=params)
                self.log.info("Statistical results written successfully")
        except Exception as e:
            if on_error == "error":
                self.log.error(f"Error while writing statistical results: {e}")
                raise e
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while writing statistical results: {e}")
            return None

    def get_trace_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        on_not_available: str | Literal["ignore", "warn", "error"] = "ignore",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ) -> gpd.GeoDataFrame | None:
        try:
            self.log.tic()
            if self._trace_results is not None:
                return self._trace_results
            if hasattr(self.simulator, "get_trace_results"):
                time_start, time_end = self.get_time_results(time_start=time_start, time_end=time_end)
                df = self.simulator.get_trace_results(time_start=time_start, time_end=time_end)
                if df is None:
                    return None
                if "t" in df.columns and pd.api.types.is_numeric_dtype(df["t"]) and "time" not in df.columns:
                    sd = self.slice.start.copy()
                    time_series = pd.to_timedelta(df["t"], unit="m") + sd._dt.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    df.insert(0, "time", time_series)
                self._trace_results = df
                self.log.info("Trace results retrieved successfully in %.2f seconds" % self.log.toc())
                return df
            else:
                if on_not_available == "error":
                    raise ValueError("Trace results not available")
                elif on_not_available.startswith("warn"):
                    self.log.warning("Trace results not available")
                return None
        except Exception as e:
            if on_error == "error":
                self.log.error(f"Error while getting trace results: {e}")
                raise e
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while getting trace results: {e}")
            return None

    def write_trace_results(
        self,
        params: dict | None = None,
        results: gpd.GeoDataFrame | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        on_not_available: str | Literal["ignore", "warn", "error"] = "ignore",
        on_no_data: str | Literal["ignore", "warn", "error"] = "warn",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ):
        try:
            df = (
                results
                if results is not None
                else self.get_trace_results(
                    time_start=time_start, time_end=time_end, on_not_available=on_not_available, on_error=on_error
                )
            )
            if df is None or len(df) == 0:
                if on_no_data == "error":
                    raise ValueError("No trace results available to write")
                elif on_no_data.startswith("warn"):
                    self.log.warning("No trace results available to write")
                    return
            else:
                if params is None:
                    params = self.parser.get(self.ini.PARAMS.TRACE_OUTPUT)
                BaseLoader.write(engine=self.engine, df=df, params=params)
                self.log.info("Trace results written successfully")
        except Exception as e:
            if on_error == "error":
                self.log.error(f"Error while writing trace results: {e}")
                raise e
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while writing trace results: {e}")
            return None

    def get_signalized_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        on_not_available: str | Literal["ignore", "warn", "error"] = "ignore",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ) -> gpd.GeoDataFrame | None:
        try:
            self.log.tic()
            if self._signalized_results is not None:
                return self._signalized_results
            if hasattr(self.simulator, "get_signalized_results"):
                time_start, time_end = self.get_time_results(time_start=time_start, time_end=time_end)
                df = self.simulator.get_signalized_results(time_start=time_start, time_end=time_end)
                if df is None:
                    return None
                if "t" in df.columns and pd.api.types.is_numeric_dtype(df["t"]) and "time" not in df.columns:
                    sd = self.slice.start.copy()
                    time_series = pd.to_timedelta(df["t"], unit="m") + sd._dt.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    df.insert(0, "time", time_series)
                self._signalized_results = df
                self.log.info("Signalized results retrieved successfully in %.2f seconds" % self.log.toc())
                return df
            else:
                if on_not_available == "error":
                    raise ValueError("Signalized results not available")
                elif on_not_available.startswith("warn"):
                    self.log.warning("Signalized results not available")
                return None
        except Exception as e:
            if on_error == "error":
                self.log.error(f"Error while getting signalized results: {e}")
                raise e
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while getting signalized results: {e}")
            return None

    def write_signalized_results(
        self,
        params: dict | None = None,
        results: gpd.GeoDataFrame | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        on_not_available: str | Literal["ignore", "warn", "error"] = "ignore",
        on_no_data: str | Literal["ignore", "warn", "error"] = "warn",
        on_error: str | Literal["ignore", "warn", "error"] = "warn",
    ) -> None:
        try:
            df = (
                results
                if results is not None
                else self.get_signalized_results(
                    time_start=time_start, time_end=time_end, on_not_available=on_not_available, on_error=on_error
                )
            )
            if df is None or len(df) == 0:
                if on_no_data == "error":
                    raise ValueError("No signalized results available to write")
                elif on_no_data.startswith("warn"):
                    self.log.warning("No signalized results available to write")
                    return
            else:
                if params is None:
                    params = self.parser.get(self.ini.PARAMS.SIGNALIZED_OUTPUT)
                BaseLoader.write(engine=self.engine, df=df, params=params)
                self.log.info("Signalized results written successfully")
        except Exception as e:
            if on_error == "error":
                self.log.error(f"Error while writing signalized results: {e}")
                raise e
            elif on_error.startswith("warn"):
                self.log.warning(f"Error while writing signalized results: {e}")
            return None

    def clear_results(self) -> None:
        if hasattr(self, "_trace_results"):
            self._trace_results = None
        if hasattr(self, "_signalized_results"):
            self._signalized_results = None
        if hasattr(self, "_stats_results"):
            self._stats_results = None

    def agg_results(self) -> gpd.GeoDataFrame | None:
        if self._agg_results is None:
            self.get_agg_results()
        return self._agg_results

    def trace_results(self) -> gpd.GeoDataFrame | None:
        if self._trace_results is None:
            self.get_trace_results()
        return self._trace_results

    def signalized_results(self) -> gpd.GeoDataFrame | None:
        if self._signalized_results is None:
            self.get_signalized_results()
        return self._signalized_results

    def stats_results(self) -> gpd.GeoDataFrame | None:
        if self._stats_results is None:
            self.get_stats_results()
        return self._stats_results


__all__ = ["AssignmentAON"]
