"""Generic Assignment Model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import geopandas as gpd
import numpy as np

from ..base.base_algorithm import BaseAlgorithm
from ..base.base_simulator import BaseSimulator
from ..model.graph_model import GraphModel, Link
from ..model.matrices_model import MatricesModel
from ..model.matrix_ass import MatrixAss
from ..model.modes_model import ModesModel
from ..model.paths_model import MultimodalPathsType, PathsModel, PathType
from ..model.simulation_interval import SimulationDatetime, SimulationInterval


@dataclass
class Iteration:
    id: int = 0
    rgap: float = 1e308
    total_travel_time: float = 0.0
    current_travel_time: float = 0.0
    total_demand: float = 0.0
    name: str = ""


@dataclass
class Slice:
    actual_start: SimulationDatetime
    start: int = 0
    end: int = 0
    time_slice: int = 0
    total_travel_time: float = 0.0
    total_demand: float = 0.0
    rgap: float = 1e308

    @property
    def intervals(self) -> list[tuple[int, int]]:
        intervals_range = list(range(self.start, self.end, self.time_slice))
        return [(x, x + self.time_slice) for x in intervals_range]

    @property
    def num_intervals(self) -> int:
        return len(self.intervals)

    @property
    def actual_end(self) -> SimulationDatetime:
        return self.actual_start.from_minutes(self.end)


@dataclass
class AssignmentSlice:
    actual_start: SimulationDatetime
    iteration: Iteration = field(default_factory=Iteration)
    interval: int = 0
    start: int = 0
    end: int = 0
    time_slice: int = 0

    @property
    def intervals(self) -> list[tuple[int, int]]:
        intervals_range = list(range(self.start, self.end, self.time_slice))
        return [(x, x + self.time_slice) for x in intervals_range]

    @property
    def num_intervals(self) -> int:
        return len(self.intervals)

    @property
    def actual_end(self) -> SimulationDatetime:
        return self.actual_start.from_minutes(self.end)


class SplitAssignmentModel(BaseAlgorithm):
    def __init__(
        self,
        simulator: BaseSimulator,
        modes: ModesModel,
        graph: GraphModel,
        ODs: MatricesModel,
        time_start: SimulationDatetime,
        time_end: SimulationDatetime,
        detectors: list | None = None,
        links_cost: str = "time",
        turns_cost: str = "time",
        nodes_cost: str = "time",
        calc_ass_matrix: bool = False,
        max_ite: int | None = None,
        max_rel_gap: float = 0.0,
        max_timeslice: int | None = None,
        use_parallel: bool = True,
        n_workers: float | None = None,
        preloaded_paths: MultimodalPathsType | None = None,
        simulation_date: datetime | None = None,
        **kwargs,
    ):
        super().__init__(use_parallel=use_parallel, n_workers=n_workers, **kwargs)

        # global settings
        self.max_ite: int = max_ite or 10_000_000
        self.max_rel_gap: float = max_rel_gap

        # Dati generali dell'intervallo di simulazione
        self.simulation_interval: SimulationInterval = SimulationInterval(time_start, time_end, simulation_date)
        self.simulation_date: SimulationDatetime = self.simulation_interval.simulation_date
        self.time_start: SimulationDatetime = self.simulation_interval.start
        self.time_end: SimulationDatetime = self.simulation_interval.end
        self.duration: int = int(self.time_end.subtract(self.time_start).total_seconds() // 60)
        self.day_type: str = self.simulation_date.day_type

        # Inizio e fine intervallo in minuti dall'inizio della giornata
        time_start_min: int = int(self.time_start.minutes_from_midnight(self.simulation_date.dt))
        time_end_min: int = int(self.time_end.minutes_from_midnight(self.simulation_date.dt))
        # Time slice massima di simulazione in minuti
        time_slice: int = int(max_timeslice or 1 * 24 * 60)  # 1 giorno massimo
        ## Aggiorna il time slice se eccede la durata dell'intervallo
        time_slice = int(min(time_end_min - time_start_min, time_slice))

        # slice globale
        self.slice: Slice = Slice(
            actual_start=self.time_start, start=time_start_min, end=time_end_min, time_slice=time_slice
        )

        # slice di assegnazione corrente
        self.assignment_slice: AssignmentSlice = AssignmentSlice(actual_start=self.time_start)
        # iterazione corrente
        self.iteration: Iteration = self.assignment_slice.iteration

        # model components
        self.simulator: BaseSimulator = simulator
        self.detectors: list = detectors or []

        self.links_cost = links_cost
        self.turns_cost = turns_cost
        self.nodes_cost = nodes_cost

        self.preloaded_paths: MultimodalPathsType | None = preloaded_paths
        self.m_paths: PathsModel = PathsModel(
            modes=list(self.modes.modes.keys()),
            paths=self.preloaded_paths,
        )

        self.calc_ass_matrix = calc_ass_matrix

        self.ODs: MatricesModel = ODs
        self.graph: GraphModel = graph
        self.graph_copy: GraphModel = graph.copy(copy_data=False, copy_graph=True)
        self.modes: ModesModel = modes.retain(list(self.ODs.modes))
        if self.graph.centroids is None:
            raise ValueError("Graph must have centroids defined.")
        self.origins: list[int] = self.graph.centroids
        self.destinations: list[int] = self.graph.centroids
        self.ass_matrix: MatrixAss | None = None
        self.eq_factors: dict[str, float] = {
            mode: params.get("eq_factor", 1) for mode, params in self.modes.modes.items()
        }

        self.infos: list[dict[str, Any]] = []

    def run(self, **kwargs):
        self.log.info("Loading parameters")
        msg = f"""Simulation Time Parameters: {self.simulation_interval}"""
        self.log.info(msg)

        num_intervals = self.slice.num_intervals
        intervals = self.slice.intervals

        if num_intervals > 1:
            self.log.info(f"Simulation will be splitted into {num_intervals} intervals: {intervals}")

        for interval, (time_start, time_end) in enumerate(self.slice.intervals):
            # aggiorno i parametri di simulazione
            self.assignment_slice.interval = interval
            self.assignment_slice.start = time_start
            self.assignment_slice.end = time_end
            self.assignment_slice.time_slice = time_end - time_start
            self.assignment_slice.actual_start = self.time_start.from_minutes(time_start)

            cs = self.assignment_slice.actual_start.strftime("%H:%M")
            ce = self.assignment_slice.actual_end.strftime("%H:%M")
            gs = self.slice.actual_start.strftime("%H:%M")
            ge = self.slice.actual_end.strftime("%H:%M")
            self.interval_name = f"{cs}-{ce} - "

            if num_intervals > 1:
                self.log.info(
                    f"{self.interval_name}Starting step simulation {interval + 1}/{num_intervals} (Global {gs}-{ge})"
                )
            else:
                self.log.info(f"{self.interval_name}Starting simulation")

            self.log.info(f"{self.interval_name}Initializing simulation")
            if self.simulator:
                self.simulator.init(self.assignment_slice.start, self.assignment_slice.end)

            self.log.info(f"{self.interval_name}Running simulation")
            self.run_internal_step()

            self.log.info(f"{self.interval_name}Finalizing simulation")
            if interval < num_intervals - 1:
                self.simulator.save_state()

            if self.calc_ass_matrix:
                self.ass_matrix = MatrixAss(
                    origins=self.graph.centroids or [],
                    destinations=self.graph.centroids or [],
                    detectors=self.detectors or [],
                    n_intervals=self.assignment_slice.num_intervals,
                    pre_intervals=0,
                )
                self.log.info(f"{self.interval_name}Calculating Assignment Matrix")
                self.calculate_ass_matrix()
            else:
                self.ass_matrix = None

            self.write_results()

        self.log.info("Finish")

    def run_internal_step(self):
        self.graph.resize_attributes(
            new_t0=self.assignment_slice.start,
            new_total_time=self.assignment_slice.time_slice,
            new_delta_t=self.graph.delta_t,
        )
        self.m_paths = PathsModel()
        calc_id = self.graph.get_index_time
        if self.preloaded_paths:
            self.log.info(f"{self.interval_name}Loading state (Paths)")
            for mode, kpaths in self.preloaded_paths.items():
                m_paths = self.m_paths[str(mode)]
                for t_start, t in enumerate(
                    range(
                        calc_id(self.assignment_slice.start, self.graph.delta_t),
                        calc_id(self.assignment_slice.end, self.graph.delta_t),
                    )
                ):
                    for path in kpaths:
                        path["t_base"] = self.graph.t0
                        path["t_start"] = t
                        path["t"] = self.graph.t0 + t
                        m_paths.add_path(path)

        if self.simulator:
            self.simulator.update(paths=self.m_paths.paths)

        # %
        self.log.info(f"{self.interval_name}Graph Initialization")

        # % inizializzo i flusso
        def reset_links(l: Link):
            l.set_value(key="time", value=l["t0"])
            l.set_value(key="flow", value=0)

        self.graph.graph.apply_links(reset_links)

        self.iteration.id = 0
        self.iteration.rgap = 1e308
        self.iteration.total_demand = 0
        self.iteration.total_travel_time = 0

        self.run_assignment()

        self.slice.total_travel_time += self.iteration.total_travel_time
        self.slice.total_demand += self.iteration.total_demand
        if self.slice.rgap < 1e307:
            self.slice.rgap = max(self.slice.rgap, self.iteration.rgap)
        else:
            self.slice.rgap = self.iteration.rgap

        if self.test_convergence():
            self.log.info("Convergence reached")
        else:
            self.log.info("Assignment completed for maximum number of iterations")

    def run_assignment(self):
        return None

    def test_convergence(self):
        if self.iteration.rgap < self.max_rel_gap:
            return True
        else:
            self.log.info("Convergence not reached, relative gap: %s", self.iteration.rgap)
            return False

    def calc_rgap(self):
        mat = self.ODs.matrix
        if self.iteration.id > 1 and self.m_paths:
            self.iteration.current_travel_time = 0
            for _, k_paths in self.m_paths.all_kpaths():
                for path in k_paths.all_kpaths():
                    if path.source == path.target:
                        continue
                    f = mat.get_od(path.mode, path.source, path.target, path.t) * self.eq_factors.get(path.mode, 1)
                    if f > 0:
                        best = min(k_paths, key=lambda path: path["tot_cost"])
                        self.iteration.current_travel_time += f * best["tot_cost"]

            if self.iteration.current_travel_time == 0:
                rgap = 0.0
            else:
                rgap = abs(self.iteration.total_travel_time - self.iteration.current_travel_time)
                rgap /= self.iteration.current_travel_time
            self.iteration.rgap = rgap
            self.log.info(f"{self.iteration.name}Relative Gap on route times: {self.iteration.rgap}")

    def update_infos(self):
        info = {
            "global_t_start": self.slice.start,
            "global_t_end": self.slice.end,
            "interval": self.assignment_slice.interval,
            "real_time_start": self.assignment_slice.actual_start,
            "real_time_end": self.assignment_slice.actual_end,
            "iteration": self.iteration.id,
            "current_time_start": self.assignment_slice.start,
            "current_time_end": self.assignment_slice.end,
            "rgap_time": None,
            "current_tt": None,
            "current_domand": None,
            "tot_tt": None,
            "tot_domand": None,
            "cpu_time": None,
            "tot_vehicles": None,
            "total_paths": self.m_paths.n_paths(),
            "unique_paths": self.m_paths.n_unique_paths(),
            "k_paths": self.m_paths.k_paths(),
        }
        info["rgap_time"] = self.iteration.rgap

        self.iteration.total_demand = sum([path["path_flow"] for path in self.m_paths.all_paths()])
        self.iteration.total_travel_time = sum(
            [path["tot_cost"] * path["path_flow"] for path in self.m_paths.all_paths()]
        )
        if self.iteration.current_travel_time:
            self.iteration.current_travel_time = self.iteration.total_travel_time
        info["current_tt"] = self.iteration.total_travel_time
        info["current_domand"] = self.iteration.total_demand
        info["tot_tt"] = self.iteration.total_travel_time + self.slice.total_travel_time
        info["tot_domand"] = self.iteration.total_demand + self.slice.total_demand
        if self.simulator and hasattr(self.simulator, "vehs"):
            if self.simulator.vehs is not None:
                tot_vehicles = len(self.simulator.vehs)
                info["tot_vehicles"] = tot_vehicles
        et = self.log.elapsed_time()
        info["cpu_time"] = et.total_seconds()
        self.infos.append(info)
        self.write_stats()

        self.log.info(f"{self.iteration.name}Total Flows: {info['tot_domand']}")
        self.log.info(f"{self.iteration.name}Last Veh*h: {info['current_tt'] / 60}")  # type: ignore
        self.log.info(f"{self.iteration.name}Total Veh*h: {info['tot_tt'] / 60}")  # type: ignore
        self.log.info(f"{self.iteration.name}Total Paths: {info['total_paths']}")
        self.log.info(f"{self.iteration.name}Unique Paths: {info['unique_paths']}")
        self.log.info(f"{self.iteration.name}K Paths: {info['k_paths']}")

        if info["tot_vehicles"] is not None:
            self.log.info(f"{self.iteration.name}Moving Vehicles: {info['tot_vehicles']}")

    def calculate_ass_matrix(self):
        self.log.info("Assignment matrix calculation...")

        def fn_calc_mat_ass(
            tasks,
            eq_factors,
            current_time_start,
            ODs,
            detectors,
        ):
            ret = []
            path: PathType
            for (source, target, t_start, mode), paths in tasks:
                for path in paths:
                    f = ODs[mode][source, target, current_time_start + t_start] * eq_factors.get(mode, 1)
                    if f <= 0:
                        continue
                    costs = path.costs
                    links = path.links
                    for t, l_idx in filter(lambda x: x[1] in detectors, zip(costs, links)):
                        ret.append(
                            (
                                source,
                                target,
                                l_idx,
                                t_start,
                                t,
                                path["path_flow"] / f,
                            )
                        )
            return ret

        tasks = self.m_paths.all_kpaths()

        n_workers = 1
        delta_t = self.graph.graph.delta_t
        assert self.ass_matrix is not None

        if n_workers > 1:
            for params in self.parallel.map(
                fn_calc_mat_ass,
                tasks,
                n_workers=n_workers,
                eq_factors=self.eq_factors,
                current_time_start=self.assignment_slice.start,
                ODs=self.ODs,
                detectors=self.ass_matrix.detectors if self.ass_matrix is not None else None,
            ):
                for source, target, l, t_start, t, flow in params:
                    t_start = int(np.floor(t_start))
                    t_enter = int(t_start + np.floor(t // delta_t))
                    self.ass_matrix.add(o=source, d=target, l=l, t_start=t_start, t_enter=t_enter, flow=flow)
        else:
            for source, target, l, t_start, t, flow in fn_calc_mat_ass(
                tasks,
                eq_factors=self.eq_factors,
                current_time_start=self.assignment_slice.start,
                ODs=self.ODs,
                detectors=self.ass_matrix.detectors if self.ass_matrix is not None else None,
            ):
                t_start = int(np.floor(t_start))
                t_enter = int(t_start + np.floor(t // delta_t))
                self.ass_matrix.add(o=source, d=target, l=l, t_start=t_start, t_enter=t_enter, flow=flow)
        self.log.info("Assignment matrix calculated")

    def get_aggregated_results_dataframe(self) -> gpd.GeoDataFrame | None:
        if self.simulator is None or not hasattr(self.simulator, "get_agg_results"):
            return None
        return self.simulator.get_agg_results(
            self.assignment_slice.start,
            self.assignment_slice.end,
            agg_int=self.ini.OUTPUT.OUTPUT_AGG_INT,
        )

    def get_trace_results(self):
        if self.simulator is None or not hasattr(self.simulator, "get_trace_results"):
            return None
        return self.simulator.get_trace_results(self.assignment_slice.start, self.assignment_slice.end)

    def get_signalized_results(self):
        if self.simulator is None or not hasattr(self.simulator, "get_signalized_results"):
            return None
        return self.simulator.get_signalized_results(self.assignment_slice.start, self.assignment_slice.end)

    def get_stats_results(self):
        if self.simulator is None or not hasattr(self.simulator, "get_stats_results"):
            return None
        return self.simulator.get_stats_results(self.assignment_slice.start, self.assignment_slice.end)

    def get_paths_results(self, t=None) -> gpd.GeoDataFrame | None:
        results = self.m_paths.paths.to_pandas(
            G=self.graph.graph,
            crs=self.graph.links.crs if self.graph.links is not None else None,
        )
        return results

    def write_results(self):
        self.log.info(f"{self.interval_name}Saving results")
        self.write_stats()
        self.write_state_paths()
        self.write_state_ass_matrix()
        self.write_paths()
        self.write_flows()
        self.write_agg_results_stats()
        self.write_trace_results()
        self.write_signal_results()

    def write_stats(self):
        pass
        """
        try:
            if self.writer.has("params.statistics"):
                self.log.info("Saving stats...")
                df = pd.DataFrame.from_dict(self.infos)
                if df is None or df.empty:
                    self.log.warning("No statistics to save")
                    return

                mode = None if self.interval == 0 else "a"
                self.writer.write(df, "params.statistics", mode=mode, first_query=self.interval == 0)
                self.log.info("Saved stats")
        except Exception as e:
            self.log.error("Failed to save statistics:", exc_info=e, stack_info=True)
        """

    def write_paths(self):
        """
        try:
            if self.save_paths:
                self.log.info("Saving paths...")
                saved = True
                paths = self.get_paths_dataframe()
                if paths is None or paths.empty:
                    self.log.warning("No paths to save")
                    return
                mode = None if self.interval == 0 else "a"
                saved = self.writer.write_paths(
                    paths,
                    mode=mode,
                    crs=self.loader.ini.CRS,
                    first_query=self.interval == 0,
                )
                paths = None
                if saved:
                    self.log.info("Saved paths")
                else:
                    self.log.warning("Failed to save paths")
        except Exception as e:
            self.log.error("Failed to save paths:", exc_info=e, stack_info=True)
        """

    def write_state_paths(self):
        """
        try:
            if self.save_state_paths:
                self.log.info("Saving state (Paths)...")
                for t in range(self.real_time_start, self.real_time_end, self.delta_t):
                    paths = list(self.m_paths.get_paths_by_t(t))
                    self.state_manager.write_state(
                        paths,
                        "paths",
                        partition=f"day_type={self.parser.get('day_type_simulation')}/t={t}",
                    )
                paths = None
                self.log.info("Saved state")
        except Exception as e:
            self.log.error("Failed to save state:", exc_info=e, stack_info=True)
        """

    def write_flows(self):
        """
        try:
            if self.save_agg_results:
                self.log.info("Saving aggregated results...")
                saved = True
                df = self.get_aggregated_results_dataframe()
                if df is not None and not df.empty:
                    ds_t = (pd.to_numeric(df["time"]) / 1000000000 % 86400) / 60
                    if df["time"].dt.tz is None:
                        df = df.assign(time=df["time"].dt.tz_localize(self.parser.ini.TZ_LOCAL).copy())
                    mode = None if self.interval == 0 else "a"
                    df["t"] = ds_t.astype("Int64")
                    saved = self.writer.write_agg_results(
                        df,
                        crs=self.loader.ini.CRS,
                        mode=mode,
                        first_query=self.interval == 0,
                    )

                    if saved:
                        self.log.info("Saved aggregated results")
                    else:
                        self.log.warning("Failed to save aggregated results")
                else:
                    self.log.warning("No aggregated results to save")
        except Exception as e:
            self.log.error("Failed to save aggregated results:", exc_info=e, stack_info=True)
        """

    def write_agg_results_stats(self):
        """
        try:
            if self.save_agg_results_stats:
                self.log.info("Saving aggregated stats...")
                saved = True
                df = self.get_aggregated_results_stats_dataframe()
                if df is not None and not df.empty:
                    mode = None if self.interval == 0 else "a"
                    saved = self.writer.write_agg_results_stats(
                        df,
                        mode=mode,
                        crs=self.loader.ini.CRS,
                        first_query=self.interval == 0,
                    )
                    if saved:
                        self.log.info("Saved aggregated stats")
                    else:
                        self.log.warning("Failed to save aggregated stats")
                else:
                    self.log.warning("No aggregated stats to save")
        except Exception as e:
            self.log.error("Failed to save aggregated stats:", exc_info=e, stack_info=True)
        """

    def write_trace_results(self):
        """
        try:
            if self.save_trace_results:
                self.log.info("Saving trace results...")
                saved = True
                df = self.get_trace_results_dataframe()
                if df is not None and not df.empty:
                    ds_t = (pd.to_numeric(df["time"]) / 1000000000 % 86400) / 60
                    if df["time"].dt.tz is None:
                        df["time"] = df["time"].dt.tz_localize(self.parser.ini.TZ_LOCAL)
                    mode = None if self.interval == 0 else "a"
                    df["t"] = ds_t.astype("Float32")
                    saved = self.writer.write_trace_results(
                        df,
                        mode=mode,
                        crs=self.loader.ini.CRS,
                        first_query=self.interval == 0,
                    )

                    if saved:
                        self.log.info("Saved trace results")
                    else:
                        self.log.warning("Failed to save trace results")
                else:
                    self.log.warning("No trace results to save")
        except Exception as e:
            self.log.error("Failed to save trace results:", exc_info=e, stack_info=True)
        """

    def write_signal_results(self):
        """
        try:
            if self.save_signal_results:
                self.log.info("Saving signal results...")
                saved = True
                df = self.get_signal_results_dataframe()
                if df is not None and not df.empty:
                    ds_t = (pd.to_numeric(df["time"]) / 1000000000 % 86400) / 60
                    if df["time"].dt.tz is None:
                        df["time"] = df["time"].dt.tz_localize(self.parser.ini.TZ_LOCAL)
                    mode = None if self.interval == 0 else "a"
                    df["t"] = ds_t.astype("Float32")
                    saved = self.writer.write_signal_results(
                        df,
                        mode=mode,
                        crs=self.loader.ini.CRS,
                        first_query=self.interval == 0,
                    )

                    if saved:
                        self.log.info("Saved signal results")
                    else:
                        self.log.warning("Failed to save signal results")
                else:
                    self.log.warning("No signal results to save")
        except Exception as e:
            self.log.error("Failed to save signal results:", exc_info=e, stack_info=True)
        """

    def write_state_ass_matrix(self):
        """
        try:
            if self.save_state_ass_matrix:
                self.log.info("Saving state (Assignment Matrix)...")

                for t_enter, mat in self.ass_matrix.get_all_matrix_by_tenter():
                    self.state_manager.write_state(
                        mat,
                        "ass_matrix",
                        mode="w",
                        partition=f"day_type={self.parser.get('day_type_simulation')}/t_enter={t_enter}",
                    )
                mat = None
                self.log.info("Saved state")
        except Exception as e:
            self.log.error("Failed to save state:", exc_info=e, stack_info=True)
        """
