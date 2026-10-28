"""Static network loading simulator based on a BPR volume-delay function."""

from __future__ import annotations

import importlib
from collections import defaultdict
from typing import Any, Callable, Hashable, Iterable

import geopandas as gpd
import numpy as np
import pandas as pd

from ..base.base_simulator import BaseSimulator
from ..model.graph_model import GraphBase
from ..model.modes_model import ModesType
from ..model.paths_model import MultimodalPathsType, PathType


class StaticSimulator(BaseSimulator):
    """Load the path flows on the network and update link costs statically.
    Load the path flows for each link of the path at a specific time step: starting time of path"""

    def __init__(self, use_parallel: bool | None = None, n_workers: float | None = None, **kwargs) -> None:
        """Build the simulator and resolve the parallel runtime to use.

        Args:
            use_parallel: If `True`, the simulator will use parallel processing.
            n_workers: Number of workers to use if running in parallel.
            **kwargs: Extra arguments forwarded to the base simulator.
        """
        super().__init__(use_parallel=use_parallel, n_workers=n_workers, **kwargs)

    def init(
        self,
        graph: GraphBase | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        paths: MultimodalPathsType | None = None,
        modes: ModesType | None = None,
        **kwargs: Any,
    ) -> StaticSimulator:
        """No state to initialize for the static simulator."""
        super().init(graph=graph, time_start=time_start, time_end=time_end, paths=paths, modes=modes, **kwargs)
        return self

    def update(
        self,
        graph: GraphBase | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        paths: MultimodalPathsType | None = None,
        modes: ModesType | None = None,
        **kwargs: Any,
    ) -> StaticSimulator:
        """No state to update for the static simulator."""
        super().update(graph=graph, time_start=time_start, time_end=time_end, paths=paths, modes=modes, **kwargs)
        return self

    def run(self, **kwargs):
        """Load the path flows on the links and recompute the link costs.

        Args:
            time_start: Start time of the simulated window.
            time_end: End time of the simulated window.

        Raises:
            ValueError: If graph or paths are not available in the workspace.
        """
        super().run(**kwargs)
        tic = self.log.tic()

        # for each path adds the path flow to the

        self.log.debug("Starting macroscopic loading...")
        for flows, mode_flows in self.app.parallel.map(
            fn=load_path_flow,
            tasks=self.paths.all_paths(),
            tstart=self.time_start,
            tend=self.time_end,
            n_workers=self.n_workers if self.use_parallel else 1,
        ):
            for (link_idx, t_start, t_cost), flow in flows.items():
                link = self.graph.get_link(link_idx)
                if link is None:
                    raise ValueError(f"Link with index {link_idx} not found in the graph.")
                idx_t = self.graph.time_index(t_start)
                idx_end = self.graph.time_index(t_cost)
                for i in range(idx_t, idx_end + 1):
                    link["flow"][i] += flow
            for (_mode, link_idx, t_start, t_cost), flow in mode_flows.items():
                link = self.graph.get_link(link_idx)
                if link is None:
                    raise ValueError(f"Link with index {link_idx} not found in the graph.")
                idx_t = self.graph.time_index(t_start)
                idx_end = self.graph.time_index(t_cost)
                for i in range(idx_t, idx_end + 1):
                    link[f"flow_{_mode}"][i] += flow
        self.log.debug("Macroscopic loading completed")

        self.log.debug("Starting VDF-based cost recomputation...")
        from ..functions.vdf import bpr

        vdfs: dict[int, Callable] = {}
        for link in self.graph.get_all_links():
            if "vdf" in link:
                function = link.get("vdf")
                if function:
                    vdf_module = importlib.import_module("..functions.vdf", package=__package__)
                    vdf_func = getattr(vdf_module, function)
                    vdfs[function] = vdf_func
        self.log.debug(f"Loaded VDF functions: {list(vdfs.keys())}")

        intervals = self.graph.get_intervals()
        default_flow = [0] * len(intervals)
        for link in self.graph.get_all_links():
            t0 = link.get("t0") or link["length"] / link["v0"]
            capacity = link.get("capacity", 0.0)
            vdf_a = link.get("vdf_a")
            vdf_b = link.get("vdf_b")
            vdf_c = link.get("vdf_c")
            vdf_d = link.get("vdf_d")
            vdf_e = link.get("vdf_e")
            vdf_f = link.get("vdf_f")
            vdf = vdfs.get(link.get("vdf", "bpr"), bpr)
            for t_idx, _ in enumerate(intervals):
                flow = link.get("flow", default_flow)[t_idx]
                cost = vdf(
                    flow=flow,
                    capacity=capacity,
                    t0=t0,
                    vdf_a=vdf_a,
                    vdf_b=vdf_b,
                    vdf_c=vdf_c,
                    vdf_d=vdf_d,
                    vdf_e=vdf_e,
                    vdf_f=vdf_f,
                )
                link["time"][t_idx] = cost
        self.log.debug("VDF-based cost recomputation completed")
        self.log.info("Macroscopic loading completed in %.2f seconds" % tic.elapsed_time())

    def save_state(self, **kwargs: Any):
        """No persistence implemented for the static simulator."""
        super().save_state(**kwargs)

    def get_agg_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        by_mode: bool = True,
        **kwargs: Any,
    ) -> gpd.GeoDataFrame:
        """Return link results aggregated by time interval and mode.

        Args:
            time_start: Start time of the requested window.
            time_end: End time of the requested window.
            agg_int: Aggregation interval length.

        Returns:
            A dataframe with flow, speed, density, travel time and saturation.

        Raises:
            ValueError: If modes, paths or graph are not set in the workspace.
        """
        assert self.workspace is not None, "Workspace must be available"
        assert self.workspace.graph_model is not None, "Graph model must be available"
        assert self.workspace.modes_model is not None, "Modes model must be available"
        G = self.workspace.graph_model.graph
        modes = set(self.workspace.modes_model.modes.keys())

        time_start = time_start if time_start is not None else self.time_start
        time_end = time_end if time_end is not None else self.time_end
        agg_int = G.delta_t
        times = np.arange(time_start, time_end, agg_int)
        ret: dict[str, list] = {
            "time": [],
            "mode": [],
            "id_link": [],
            "flow": [],
            "speed": [],
            "density": [],
            "travel_time": [],
            "saturation": [],
            "geometry": [],
        }
        if by_mode:
            for mode in modes:
                ret[f"flow_{mode}"] = []
        list_time = ret["time"]
        list_mode = ret["mode"]
        list_id_link = ret["id_link"]
        list_flow = ret["flow"]
        list_speed = ret["speed"]
        list_density = ret["density"]
        list_travel_time = ret["travel_time"]
        list_saturation = ret["saturation"]
        list_geometry = ret["geometry"]

        for time in times.tolist():
            t_idx = G.time_index(time)
            for link in G.get_all_links():
                idx = link["idx"]
                flow_eq = link["flow"][t_idx]
                travel_time = link["time"][t_idx]
                speed = link["length"] / travel_time * 60
                density = flow_eq / speed
                c = link["capacity"]
                saturation = flow_eq / c if c != 0 else float("nan")
                geometry = link["geometry"]

                list_time.append(time)
                list_mode.append("all")
                list_id_link.append(idx)
                list_flow.append(flow_eq)
                list_speed.append(speed)
                list_density.append(density)
                list_travel_time.append(travel_time)
                list_saturation.append(saturation)
                list_geometry.append(geometry)

                if not by_mode:
                    continue

                for mode in modes:
                    ret[f"flow_{mode}"].append(link["flow_" + mode][t_idx])
        dtype = {
            "time": float,
            "mode": str,
            "flow": float,
            "speed": float,
            "density": float,
            "travel_time": float,
            "saturation": float,
        }
        if by_mode:
            for mode in modes:
                dtype[f"flow_{mode}"] = float
        else:
            ret.pop("mode")

        crs = self.ini.GENERAL.CRS_CALC
        df = pd.DataFrame(ret)
        return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=df["geometry"], crs=crs).astype(dtype)


def load_path_flow(
    tasks: Iterable[PathType], tstart: float, tend: float
) -> tuple[dict[tuple[Hashable, int, int], int], dict[tuple[str, Hashable, int, int], int]]:
    """Accumulate total and per-mode link flows for a chunk of paths."""
    flows: dict[tuple[Hashable, int, int], int] = defaultdict(int)
    mode_flows: dict[tuple[str, Hashable, int, int], int] = defaultdict(int)
    for path in tasks:
        t = path["t"]
        if not (tstart <= t < tend):
            continue
        cost = path.tot_cost + t
        mode = str(path["mode"])
        for link_idx in path.get_links():
            flows[(link_idx, int(t), int(cost))] += path["path_flow"]
            mode_flows[(mode, link_idx, int(t), int(cost))] += path["path_flow"]
    return flows, mode_flows


__all__ = ["StaticSimulator"]
