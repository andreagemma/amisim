# -*- coding: utf-8 -*-
"""
Created on Wed Oct 27 11:27:43 2021

@author: Natalia
"""

from __future__ import annotations

import math
import time
from operator import itemgetter
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import get_x, get_y, line_interpolate_point

from ...base.base_simulator import BaseSimulator
from ...model.events_model import EventsType
from ...model.graph_model import GraphBase, Link
from ...model.matrices_model import MultiModalDynamicMatrix
from ...model.modes_model import ModesType
from ...model.paths_model import MultimodalPathsType
from ...model.simulation_interval import SimulationDatetime
from ...utils.geom import ST_Multi
from .car import Car

__all__ = ["MicroSimulator", "YieldNode", "SigNode", "Car"]

isnan = pd.isna

from operator import attrgetter

sort_fun = attrgetter("c_l_ti")  # use operator since it's faster than lambda


class SigNode:
    def __init__(self, graph: GraphBase, id: int, node: dict, simustep: int):
        self.G: GraphBase = graph
        self.id = id
        self.Cycle = node["cycle"]
        self.phases: dict[tuple, dict] = {}
        self.res: list[list[Any]] = []

        for phase in node["phases"]:
            self.G.get_link(phase["from_link"])["signalized"] = True  # type: ignore

            key = (
                (phase["from_link"], phase["via_link"], phase["to_link"])
                if "via_link" in phase
                else (phase["from_link"], phase["to_link"])
            )

            self.phases[key] = phase
            self.G["signalized_links"].add(phase["from_link"])
            st: dict[str, Any] = {}
            self.G["signalized_turns"][key] = st
            st["state"] = "green"
            st["type"] = phase["type"]

            t_start = phase["t_start"]
            t_end = phase["t_end"]
            if t_start % simustep != 0:
                phase["t_start"] = -(-t_start // simustep) * simustep
            if t_end % simustep != 0:
                phase["t_end"] = -(-t_end // simustep) * simustep

            if phase["type"] == "left_turn":
                if phase["permitted"] == True:
                    st["permitted"] = True
                    st["opposite_turn"] = phase["opposite_turn"]
                    st["permitted_movs"] = 2

    def update_cap(self, t, t1):
        "Signalized node model"
        tt = t1 * 60 % self.Cycle
        for key, phase in self.phases.items():
            st = self.G["signalized_turns"][key]
            self.res.append(
                [
                    phase["from_link"],
                    phase["to_link"],
                    t1,
                    st["state"],
                    phase["type"],
                ]
            )

            if tt == phase["t_start"]:
                st["state"] = "green"

            elif tt == phase["t_end"]:
                st["state"] = "red"

    def update_graph(self, new_graph):
        for k, v in self.G["signalized_turns"].items():
            new_graph["signalized_turns"][k] = v
        self.G = new_graph


class YieldNode:
    def __init__(self, graph: GraphBase, node: int, lim: float | None = None, filt: float | None = None):
        self.G = graph
        self.idx = node
        bws = graph.get_node_neighbors(idx=node, include_in_links=True, include_out_links=False)

        bws_links = sorted(bws, key=lambda link: link["v0"])

        self.main_links = [bws_links[1]]
        self.yield_links = [bws_links[0]]
        self.lim = lim if lim else 1
        self.filt = filt if filt else 10

    def update_cap(self):
        "Yield capacity model"
        main_cap = sum([ix["inflow_cap"] * self.filt for ix in self.main_links])
        main_flow = sum([ix["ent_veh_f"] * self.filt for ix in self.main_links])
        perc = (1 - self.lim) * math.exp(-5.4 / main_cap * main_flow) + self.lim

        for link in self.yield_links:
            link["inflow_cap"] *= perc

        p = sum([link["l_queue"] / link["length"] for link in self.yield_links])
        if p > 0.3:
            for link in self.main_links:
                link["inflow_cap"] *= 0.85

    def update_graph(self, new_graph):
        self.G = new_graph
        bws = new_graph.get_node_neighbors(idx=self.idx, include_in_links=True, include_out_links=False)

        bws_links = sorted(bws, key=lambda link: link["v0"])

        self.main_links = [bws_links[1]]
        self.yield_links = [bws_links[0]]


class MicroSimulator(BaseSimulator):
    def __init__(self, use_parallel=False, n_workers=1, **kwargs):
        super().__init__(use_parallel=use_parallel, n_workers=n_workers, **kwargs)
        self.simustep = self.ini.SIMULATOR.SIMU_STEP  # [s] simulation step in seconds
        self.agg_int = self.ini.OUTPUT.OUTPUT_AGG_INT  # [m] aggregation of results
        self.deltat = self.simustep / 60  # [min] simulation delta t

        self.ints_agg = int(self.agg_int * 60 / self.simustep)  # number of simusteps within agg_int
        self.t_slice: int  # [min] duration of a simulation slice # inizializzato in init()
        self.ODs: MultiModalDynamicMatrix
        self.origini: list[Any] = []
        self.destinazioni: list[Any] = []
        self.monitored_links: list[Any] = []
        self.yield_nodes: list[YieldNode] = []
        self.ind_res = False
        self.mon_veh: float = 0.0
        self.signalized_nodes: list[SigNode] = []
        self.monitored_flows: list[Any] = []
        self.events: EventsType = {}
        self.filt = 10

        self.l_car = self.ini.SIMULATOR.CAR_LENGTH / 1000
        self.k_jam = 1 / self.l_car
        self.min_speed = self.ini.SIMULATOR.MIN_SPEED
        self.coef = self.ini.SIMULATOR.COEFFICENTS
        self.links_list: list
        self.preload = False

        self.ass_results: list[list] = []
        self.t = 1
        self.vehs: list[Car] = []
        Car.ini = self.ini
        Car.rng = self.rng
        Car.lt1 = self.ini.SIMULATOR.LT1 / 60
        Car.lt2 = self.ini.SIMULATOR.LT2 / 60
        self.time_index: int = 0
        self.fields: list[str] = []
        self.df_agg_results: gpd.GeoDataFrame | None = None
        self.df_stats_results: gpd.GeoDataFrame | None = None
        self.df_trace_results: gpd.GeoDataFrame | None = None
        self.df_signalized_results: gpd.GeoDataFrame | None = None
        self.debug: bool = self.ini.GENERAL.DEBUG
        self.num: int = 0

    def init(
        self,
        graph: GraphBase | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        paths: MultimodalPathsType | None = None,
        modes: ModesType | None = None,
        matrix: MultiModalDynamicMatrix | None = None,
        centroids: set[Any] | list[Any] | None = None,
        monitored_links: list[Any] | None = None,
        yield_nodes: list[YieldNode] | None = None,
        signalized_nodes: list[dict[str, Any]] | None = None,
        ind_res: bool | None = None,
        mon_veh: bool | None = None,
        events: EventsType | None = None,
        **kwargs: Any,
    ) -> MicroSimulator:
        super().init(
            graph=graph.copy() if graph is not None else None,
            time_start=time_start,
            time_end=time_end,
            paths=paths,
            modes=modes,
            **kwargs,
        )
        assert self.graph is not None, "The graph must be available"
        assert self.workspace is not None, "The workspace must be available"
        assert self.workspace.graph_model is not None, "The graph model must be available"
        assert self.workspace.links_sets_model is not None, "The links sets model must be available"
        assert self.workspace.events_model is not None, "The events model must be available"
        assert self.workspace.traffic_lights_model is not None, "The traffic lights model must be available"
        assert self.workspace.modes_model is not None, "The modes model must be available"
        assert self.workspace.matrices_model is not None, "The matrices model must be available"

        self.t_slice = self.graph.delta_t  # [min] duration of a simulation slice
        if matrix is not None:
            self.ODs = matrix

        self.graph["signalized_turns"] = {}
        self.graph["signalized_links"] = set()
        self.links_list = list(self.graph.get_all_links_idx())  # list of the links

        if centroids is not None:
            self.origini = list(centroids)[:]
            self.destinazioni = list(centroids)[:]

        self.monitored_links = monitored_links if monitored_links else []
        self.yield_nodes = yield_nodes if yield_nodes else []
        self.ind_res = ind_res if ind_res is not None else self.ini.OUTPUT.OUTPUT_IND_RES
        self.mon_veh = mon_veh if mon_veh is not None else self.ini.OUTPUT.MONITORED_VEH
        self.events = events if events is not None else self.workspace.events_model.events
        signalized_nodes = signalized_nodes if signalized_nodes else self.workspace.traffic_lights_model.traffic_lights
        self.signalized_nodes = [
            SigNode(id=i, node=s_n, graph=self.graph, simustep=self.simustep) for i, s_n in enumerate(signalized_nodes)
        ]

        Car.ind_res = self.ind_res
        Car.mon_veh = self.mon_veh
        self.sim_duration = self.time_end - self.time_start  # [min] duration of
        self.simint = int(self.sim_duration / self.deltat)  # number of simulation steps
        self.t = int(self.time_start * self.simustep)
        self.t_i = self.t
        self.t_f = self.t_i + self.simint
        self.set_closures(self.time_start, self.time_end)
        self.int_update = int(self.t_slice // self.deltat)

        self.modes_codes = sorted(self.modes.keys())

        return self

    def update(
        self,
        graph: GraphBase | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        paths: MultimodalPathsType | None = None,
        modes: ModesType | None = None,
        matrix: MultiModalDynamicMatrix | None = None,
        centroids: set[Any] | list[Any] | None = None,
        monitored_links: list[Any] | None = None,
        yield_nodes: list[YieldNode] | None = None,
        signalized_nodes: list[dict[str, Any]] | None = None,
        ind_res: bool | None = None,
        mon_veh: bool | None = None,
        events: EventsType | None = None,
        **kwargs: Any,
    ) -> MicroSimulator:
        super().update(
            graph=graph,
            time_start=time_start,
            time_end=time_end,
            paths=paths,
            modes=modes,
            **kwargs,
        )
        if graph is not None:  # updateting if change graph
            self.t_slice = self.graph.delta_t  # [min] duration of a simulation slice
            self.graph["q_trace"] = []
            self.graph["signalized_turns"] = {}
            self.graph["signalized_links"] = set()
            self.links_list = list(self.graph.get_all_links_idx())  # list of the links

        if modes is not None:
            self.modes_codes = sorted(modes.keys())

        if matrix is not None:
            self.ODs = matrix

        if centroids is not None:
            self.origini = list(centroids)[:]
            self.destinazioni = list(centroids)[:]

        if monitored_links is not None:
            self.monitored_links = monitored_links

        if yield_nodes is not None:
            self.yield_nodes = yield_nodes

        if ind_res is not None:
            self.ind_res = ind_res
            Car.ind_res = self.ind_res
        if mon_veh is not None:
            self.mon_veh = mon_veh
            Car.mon_veh = self.mon_veh

        if events is not None:
            self.events = events

        if signalized_nodes is not None:
            self.signalized_nodes = [
                SigNode(id=i, node=s_n, graph=self.graph, simustep=self.simustep)
                for i, s_n in enumerate(signalized_nodes)
            ]

        self.sim_duration = self.time_end - self.time_start  # [min] duration of
        self.simint = int(self.sim_duration / self.deltat)  # number of simulation steps
        self.t = int(self.time_start * self.simustep)
        self.t_i = self.t
        self.t_f = self.t_i + self.simint
        # self.set_closures(self.time_start, self.time_end)
        self.int_update = int(self.t_slice // self.deltat)
        return self

    def set_closures(self, time_start, time_end):
        "Set closure for the ramps"

        closures = ["ramps", "heavy_vehicles_ban"]
        for event in closures:
            for measure in self.events.get(event, []):
                if (measure["start_t"] >= time_start) & (measure["start_t"] <= time_end):
                    ints = self.graph["num_intervals"]
                    for interval in range(ints):
                        t_start = time_start + interval * self.t_slice
                        t_end = t_start + self.t_slice
                        if (measure["start_t"] <= t_start) & (measure["end_t"] >= t_end):
                            for l in measure["arc_list"]:
                                link = self.graph.get_link(l)
                                if link is not None:
                                    link["time"][interval] = 9999999

    def close_link(self, t):
        "Close links"
        for measure in self.events.get("closures", []):
            if t == measure["start"]:
                for l in measure["arc_list"]:
                    link = self.graph.get_link(l)
                    if link is None:
                        self.log.warning(f"Link {l} not found in graph.")
                        continue
                    link["storage_cap"] = 0
                    link["disabled"] = True

            elif t == measure["end"] - self.deltat:
                for l in measure["arc_list"]:
                    link = self.graph.get_link(l)
                    if link is None:
                        self.log.warning(f"Link {l} not found in graph.")
                        continue
                    link["storage_cap"] = max(1, (link["length"] * link["lanes"]) / self.l_car)
                    link["disabled"] = False

    def set_speedlims(self, t):
        "Update speed limits"
        for measure in self.events.get("speed_limits", []):
            if t == measure["start_t"]:
                speed = measure["params"]["speed"]
                for l in measure["arc_list"]:
                    link = self.graph.get_link(l)
                    if link is None:
                        self.log.warning(f"Link {l} not found in graph.")
                        continue
                    link["v0"] = speed
                    link["speed_limit"] = speed
            elif t == measure["end_t"]:
                for l in measure["arc_list"]:
                    link = self.graph.get_link(l)
                    if link is None:
                        self.log.warning(f"Link {l} not found in graph.")
                        continue
                    link["v0"] = link["default_v0"]
                    link["speed_limit"] = link["default_v0"]

    def update_meteo(self, t):
        "Update meteo events"
        for measure in self.events.get("weather", []):
            if t == measure["start_t"]:
                params = measure["params"]
                alpha_pioggia = self.coef["Pioggia"][str(params["rain"])]
                alpha_nebbia = self.coef["Nebbia"][str(params["fog"])]
                alpha_vento = self.coef["Vento"][str(params["wind"])]
                alpha_neve = self.coef["Neve"][str(params["snow"])]
                alpha_comb = (
                    alpha_pioggia
                    + alpha_nebbia
                    + alpha_vento
                    + alpha_neve
                    + alpha_nebbia * alpha_pioggia
                    + alpha_nebbia * alpha_neve
                )

                F = max(0.5, 1 - alpha_comb)
                for l in measure["arc_list"]:
                    link = self.graph.get_link(l)
                    if link is not None:
                        link["v0"] = link["v0"] * F

            elif t == measure["end_t"]:
                for l in measure["arc_list"]:
                    link = self.graph.get_link(l)
                    if link is not None:
                        link["v0"] = link["speed_limit"]

    def close_lanes(self, t):
        "Update lanes closures"
        for measure in self.events.get("lanes", []):
            if t == measure["start"]:
                for l in measure["arc_list"]:
                    link = self.graph.get_link(l)
                    if link is None:
                        continue
                    tl = measure["params"]["type_lanes"]
                    if isinstance(link, str):  # per gestire paramatri tipo ["S","C"]
                        tl = [tl]
                    num_lanes = [self.coef["Corsia"][l] for l in tl]
                    num_lanes = max(num_lanes)  # i caso multiplo allora prende il massimo (veirificare se ha senso)
                    default_capacity = (
                        (link["capacity"] / 60 * self.deltat) / link["default_lanes"]
                        if link["default_lanes"] > 0
                        else 0
                    )
                    link["cap_dt"] = link["cap_dt"] - num_lanes * default_capacity
                    link["lanes"] -= max(num_lanes, 0)
                    link["storage_cap"] = max(1, (link["length"] * link["lanes"]) / self.l_car)
                    link["n_cl_lanes"] += 1

                    if link["n_cl_lanes"] == link["default_lanes"]:
                        link["disabled"] = True
                        link["storage_cap"] = 0

            elif t == measure["end_t"]:
                for l in measure["arc_list"]:
                    link = self.graph.get_link(l)
                    if link is None:
                        self.log.warning(f"Link {l} not found in graph.")
                        continue
                    num_lanes = self.coef["Corsia"][measure["params"]["type_lanes"]]
                    default_capacity = (
                        (link["capacity"] / 60 * self.deltat) / link["default_lanes"]
                        if link["default_lanes"] > 0
                        else 0
                    )
                    link["n_cl_lanes"] -= 1
                    link["cap_dt"] = link["cap_dt"] + num_lanes * default_capacity
                    link["lanes"] += num_lanes
                    link["storage_cap"] = max(1, (link["length"] * link["lanes"]) / self.l_car)

                    if link["n_cl_lanes"] == 0:
                        link["disabled"] = False
                        link["lanes"] = link["default_lanes"]
                        link["storage_cap"] = max(1, (link["length"] * link["lanes"]) / self.l_car)
                        link["cap_dt"] = link["capacity"] / 60 * self.deltat

    def ini_links(self, link: Link):

        if not self.preload:
            if isnan(link["length"]) or link["length"] == 0:
                link["length"] = 0.1

            if isnan(link["v0"]) or link["v0"] == 0:
                link["v0"] = 80

            if isnan(link["t0"]) or link["t0"] == 0:
                link["t0"] = 0.001

            if link["connector"] == 1:
                link["lanes"] = 100

            link["sp"] = []

            link.reset("flow", 0.0)
            for mode in self.modes_codes:
                link.reset(f"flow_{mode}", 0.0)

        link["cap_dt"] = link["capacity"] / 60 * self.deltat  # [veh/deltat]
        link["inflow_cap"] = link["cap_dt"]

        link["ex_veh"] = 0
        link["ent_veh"] = 0
        for m in self.modes_codes:
            link[f"ex_veh_{m}"] = 0
            link[f"ent_veh_{m}"] = 0

        if self.preload:
            pre_link = self.preload_graph.get_link(link["idx"])
            if pre_link is None:
                self.log.warning(f"Preload link {link['idx']} not found in preload graph.")
                return
            link["storage_cap"] = pre_link["storage_cap"]

            link["que_vehs"] = pre_link["que_vehs"]
            link["mov_vehs"] = pre_link["mov_vehs"]

            link["speed"] = pre_link["speed"]
            link["cum_density"] = pre_link["cum_density"]
            link["ta"] = pre_link["ta"]

            link["l_queue"] = pre_link["l_queue"]
            link["tt"] = pre_link["tt"]
            link["cum_tt"] = pre_link["cum_tt"]

            link["cum_que_vehs"] = pre_link["cum_que_vehs"]
            link["cum_mov_vehs"] = pre_link["cum_mov_vehs"]
            link["max_que"] = pre_link["max_que"]

            link["n_updates"] = pre_link["n_updates"]
            link["cum_tt_delta"] = pre_link["cum_tt_delta"]
            link["n_updates_delta"] = pre_link["n_updates_delta"]

            link["disabled"] = False
            link["ksi"] = link["ta"] / self.deltat

            link["t0"] = link["length"] / link["speed"] * 60

        else:
            link["storage_cap"] = max(1, (link["length"] * link["lanes"]) / self.l_car)

            link["que_vehs"] = 0
            link["mov_vehs"] = 0

            link["speed"] = link["v0"]
            link["cum_density"] = 0
            link["ta"] = link["t0"]

            link["cum_cap"] = 0
            link["cum_veh"] = 0
            link["density"] = 0

            link["l_queue"] = 0
            link["tt"] = link["t0"]
            link["cum_tt"] = link["t0"]

            link["cum_que_vehs"] = 0
            link["cum_mov_vehs"] = 0
            link["max_que"] = 0

            link["n_updates"] = 1
            link["cum_tt_delta"] = link["t0"]
            link["n_updates_delta"] = 1

            link["disabled"] = False
            link["ksi"] = min(1, link["ta"] / self.deltat)

            link["t0"] = link["length"] / link["speed"] * 60

            link["last_speed"] = link["speed"]
            link["cum_speed"] = link["v0"]
            link["ex_q_veh"] = 0
            link["default_lanes"] = link["lanes"]
            link["default_v0"] = link["v0"]
            link["speed_limit"] = link["v0"]
            link["n_cl_lanes"] = 0

            if self.debug:
                link["ex_vehs"] = []
                link["ent_vehs"] = []
                link["storage"] = []
                link["movs_vehs"] = []
                link["speed_obs"] = []

        if link["ta"] < 6 / 60:
            link["ta"] = 0.0001
            link["t0"] = 0.0001
            link["cap_dt"] = 9999999

    def update_time_index(self):
        self.time_index = self.graph.time_index(int(self.inx_update * self.t_slice))

    def initialize_graph(self):
        "Initialize graph for the simulation"
        self.inx_update = 0
        self.t_slice = self.graph.delta_t
        self.update_time_index()

        self.results: list[list] = []
        self.df_agg_results = None
        self.df_stats_results = None
        self.df_trace_results = None
        self.df_signalized_results = None

        self.graph.reset_links("flow", 0)
        for mode in self.modes:
            self.graph.reset_links(name=f"flow_{mode}", value=0)

        self.graph.apply_links(self.ini_links)

        if self.preload:
            self.log.debug(
                f"Preloading vehicles (len={len(self.preload_vehs)}) and signalized nodes (len={len(self.preload_signalized_nodes)})"
            )
            self.vehs = self.preload_vehs
            [veh.update_graph(self.graph) for veh in self.vehs]
            if self.preload_signalized_nodes:
                [sign.update_graph(self.graph) for sign in self.preload_signalized_nodes]
                self.signalized_nodes = self.preload_signalized_nodes
            if self.preload_yield_nodes:
                [yn.update_graph(self.graph) for yn in self.preload_yield_nodes]
                self.yield_nodes = self.preload_yield_nodes

            self.res_flow = self.preload_res_flow
            self.num = self.preload_num
            self.preload = False

        else:
            self.vehs = []
            self.num = 0
            self.res_flow = {}
            for o in self.origini:
                for d in self.destinazioni:
                    if o != d:
                        self.res_flow[o, d] = 0.0
                "Update results vectors with simulated times"
        self.fields = [
            "idx",
            "ent_veh",
            "ex_veh",
        ]
        for m in self.modes_codes:
            self.fields.append(f"ent_veh_{m}")
            self.fields.append(f"ex_veh_{m}")
        self.fields += [
            "max_que",
            "cum_mov_vehs",
            "cum_que_vehs",
            "cum_speed",
            "cum_density",
            "cum_tt",
            "n_updates",
        ]

    def run(self, **kwargs):

        self.results = []
        self.ass_results = []

        self.initialize_graph()

        tstart = self.time_start
        tend = self.time_end
        time_ = time.time()
        self.emission_model(self.ODs, tstart, tend)

        ini_t = self.t_i
        fin_t = self.t_f

        for t in range(ini_t, fin_t):
            t1 = tstart + (t - ini_t) * self.deltat
            self.update_network(t1)
            self.vehs = self.sim_step(t1, self.vehs)

            if t > ini_t and (t - ini_t) % self.ints_agg == 0:
                self.update_res(t1 - self.ints_agg * self.deltat)
                self.graph.apply_links(self.reset_flags)
                self.reset_turns()

            if t > ini_t and (t - ini_t) % self.int_update == 0:
                # print("moving vehicles %d" % (len(self.vehs)))
                self.graph.apply_links(self.t_compute)

                self.inx_update += 1
                self.update_time_index()
                self.emission_model(self.ODs, tstart, tend)
                self.log.debug("Updated time for t=%s", SimulationDatetime.min2hhmm(int(t1)))

            self.update_ta(t, t1)
        t = fin_t
        t1 = int(tstart + (t - ini_t) * self.deltat)
        if t > ini_t and (t - ini_t) % self.ints_agg == 0:
            self.update_res(t1 - self.ints_agg * self.deltat)
            self.graph.apply_links(self.reset_flags)

        if t > ini_t and (t - ini_t) % self.int_update == 0:
            # print("moving vehicles %d" % (len(self.vehs)))
            self.graph.apply_links(self.t_compute)

            self.inx_update += 1
            self.update_time_index()
            self.emission_model(self.ODs, tstart, tend)
            self.log.debug("Update timed for t=%s", SimulationDatetime.min2hhmm(t1))

        self.ass_results.extend(self.results)

        elapsed = time.time() - time_

        self.log.info("Simulated %d vehicles in %2.f seconds" % (self.num, elapsed))

    def emission_model(self, od: MultiModalDynamicMatrix, tstart: int, tend: int):
        "Emission model"
        ints = self.graph.num_intervals
        n = self.inx_update
        if n < ints:
            for mode, mat in od.get_all_matrices():
                eq_factor = self.modes.get(mode, {}).get("eq_factor", 1.0)
                for o in self.origini:
                    for d in self.destinazioni:
                        if o != d:
                            fod = (
                                mat[o, d, tstart + n * self.t_slice] * (self.t_slice / 60) * eq_factor
                                + self.res_flow[o, d]
                            )

                            if fod > 0.5:  # at least one vehicle is created
                                fod_out = int(round(fod))
                                p = [
                                    path["path_flow"] / fod
                                    for path in self.paths.paths(
                                        source=o,
                                        target=d,
                                        t_start=n * self.t_slice,
                                        mode=mode,
                                    )
                                ]
                                k = len(p)
                                tot_flow = sum(p)
                                if k == 0:
                                    self.log.warning(
                                        "No paths available for origin %d and destination %d at time %s",
                                        o,
                                        d,
                                        SimulationDatetime.min2hhmm(tstart + n * self.t_slice),
                                    )
                                    continue
                                if tot_flow > 0:
                                    f = self.rng.choice(
                                        range(int(k)), p=[pi / tot_flow for pi in p], size=fod_out
                                    ).tolist()
                                else:
                                    f = self.rng.choice(range(int(k)), size=fod_out).tolist()

                                delta_emi = self.t_slice / fod_out
                                self.res_flow[o, d] = fod - fod_out

                                for veh in range(len(f)):
                                    path = self.paths.path(
                                        source=o,
                                        target=d,
                                        t_start=n * self.t_slice,
                                        mode=mode,
                                        k=f[veh],
                                    )

                                    if (not path) or len(path["links"]) == 0:
                                        self.log.warning(
                                            "No path available for origin %d and destination %d at time %s",
                                            o,
                                            d,
                                            SimulationDatetime.min2hhmm(tstart + n * self.t_slice),
                                        )
                                        continue

                                    self.num += 1

                                    if len(path["links"]) > 1:
                                        veh1 = Car(
                                            self.num,
                                            tstart + n * self.t_slice + delta_emi * veh,
                                            path,
                                            self.graph,
                                            self.deltat,
                                            mode=mode,
                                        )
                                        self.vehs.append(veh1)
                            else:
                                self.res_flow[o, d] = fod

    def update_network(self, t):
        "Update network based on the parameters"
        self.close_lanes(t)
        self.set_speedlims(t)
        self.update_meteo(t)
        self.close_link(t)

    def sim_step(self, t: float, vehs: list[Car]):
        "Simulation step"

        vehs = self.order_positions(vehs)
        vehs = list(filter(lambda v: v.move(t), vehs))

        return vehs

    def update_res(self, t):
        "Update results vectors with simulated times"
        res = [[t] + list(itemgetter(*self.fields)(link)) for link in self.graph.get_all_links()]
        self.results += res

    def update_nodes(self, t, t1):
        "Update capacities of links of Yeild and Signalized Junctions"
        if self.yield_nodes:
            [node.update_cap() for node in self.yield_nodes]  # update yield nodes
        if self.signalized_nodes:
            [node.update_cap(t, t1) for node in self.signalized_nodes]  # update yield nodes
        # ts_cap() #update signalized nodes

    def save_state(self, **kwargs: Any):

        self.preload = True
        self.preload_vehs = self.vehs
        self.preload_res_flow: dict = self.res_flow
        self.preload_graph: GraphBase = self.graph
        self.preload_signalized_nodes: list[SigNode] = self.signalized_nodes
        self.preload_yield_nodes: list[YieldNode] = self.yield_nodes
        self.preload_num = self.num
        self.t = self.t_f

        return

    def yield_cap(self, yield_nodes, G):
        "Yeild capacity model"
        for node in yield_nodes:
            main_flow = sum([G.get_link(ix)["ent_veh"] for ix in node["main_links"]]) * 60 / self.deltat
            main_cap = sum([G.get_link(ix)["cap_dt"] for ix in node["main_links"]]) * 60 / self.deltat
            perc = (1 - node["lim"]) * math.exp(-5.4 / main_cap * main_flow) + node["lim"]

            for link in node["yield_links"]:
                G.get_link(link)["inflow_cap"] = G.get_link(link)["cap_dt"] * perc

            p = sum([G.get_link(ix)["l_queue"] / G.get_link(ix)["length"] for ix in node["yield_links"]])
            if p > 0.3:
                for link in node["main_links"]:
                    G.get_link(link)["inflow_cap"] = G.get_link(link)["cap_dt"] * 0.85

    def order_positions(self, vehs: list[Car]):
        "FIFO rule ensured"
        # vehs = [veh for veh in vehs if veh.status!="arrived"]

        vehs = sorted(vehs, key=sort_fun)
        return vehs

    def update_ta(self, t, t1):
        "Update speeds on links based on observed vehicles"
        self.update_nodes(t, t1)
        # self.G.apply_links(self.update_capacities)
        self.graph.apply_links(self.update_times)
        # self.G.apply_onset_links(self.G["links_set"], self.update_times)

    def t_compute(self, link: Link):
        "Compute average of the travel time during time interval"
        link["time"][self.time_index] = link["cum_tt_delta"] / link["n_updates_delta"]
        link["cum_tt_delta"] = link["t0"]
        link["n_updates_delta"] = 1

    def reset_flags(self, link: Link):
        "Reset aggregated values"
        link["ex_veh"] = 0
        link["ent_veh"] = 0
        link["ex_veh_h"] = 0
        link["ent_veh_h"] = 0
        link["speed"] = link["v0"]
        link["cum_speed"] = link["v0"]
        link["cum_que_vehs"] = 0
        link["max_que"] = link["que_vehs"]
        link["cum_mov_vehs"] = 0
        link["cum_density"] = 0
        link["cum_tt"] = link["t0"]
        link["n_updates"] = 1

    def reset_turns(self):
        "Reset aggregated values"
        for turn in self.graph["signalized_turns"].values():
            if turn["type"] == "left_turn":
                turn["permitted_movs"] = 2

    def update_capacities(self, link: Link):
        "Update capacity for next time interval"
        if link["inflow_cap"] < 1:
            link["inflow_cap"] += link["cap_dt"]
        else:
            link["inflow_cap"] = link["cap_dt"]

    def update_times(self, link: Link):
        "Update capacity for next time interval"
        link["ex_q_veh"] = 0
        if self.debug:
            link["ex_vehs"].append(link["ex_veh"])
            link["ent_vehs"].append(link["ent_veh"])
            link["storage"].append(link["storage_cap"])

        if link["inflow_cap"] < 1:
            link["inflow_cap"] += link["cap_dt"]
        else:
            link["inflow_cap"] = link["cap_dt"]

        if ((link["disabled"]) or (link["mov_vehs"] > 0) or (link["que_vehs"] > 0)) & (not (link["connector"] == 1)):
            "Update times on links"

            free_link = link["length"] - link["l_queue"]
            density = 0.0
            speed = 0.0
            if not link["disabled"]:
                if free_link > 0:
                    ff_speed = link["v0"]
                    nv = link["mov_vehs"]
                    if nv >= 0:  # UPDATE: GEMMA
                        density = (nv) / (free_link * link["lanes"]) if link["lanes"] > 0 else float("inf")
                    else:
                        density = (nv) / (free_link * link["lanes"]) if link["lanes"] > 0 else 0
                    speed = ff_speed * math.exp(-(1 / link["alpha"]) * (density / link["rcr"]) ** link["alpha"])

                else:
                    density = self.k_jam
                    speed = self.min_speed

                speed = max(self.min_speed, speed)

            if link["disabled"]:
                speed = 0.0000001
                link["storage_cap"] = 0
                density = 0

            link["density"] = density
            speed = link["last_speed"] * (self.filt - 1) / self.filt + speed * (1) / self.filt
            link["last_speed"] = speed

            link["speed"] = speed
            link["cum_speed"] += speed
            link["cum_density"] += density
            link["ta"] = (link["length"] / speed) * 60
            link["ksi"] = min(1, link["ta"] / self.deltat)
            link["l_queue"] = (
                min(link["length"], (link["que_vehs"] * self.l_car / link["lanes"])) if link["lanes"] > 0 else 0
            )  # UPDATE: GEMMA
            link["tt"] = link["ta"] + link["que_vehs"] / link["cap_dt"]
            link["cum_tt"] += link["tt"]
            link["cum_que_vehs"] += link["que_vehs"]
            link["cum_mov_vehs"] += link["mov_vehs"]
            link["max_que"] = max(link["max_que"], link["que_vehs"])

            link["n_updates"] += 1
            link["cum_tt_delta"] += link["tt"]
            link["n_updates_delta"] += 1

            if link["ta"] < 6 / 60:
                link["ta"] = 0.0001
                link["cap_dt"] = 9999999
        if self.debug:
            link["movs_vehs"].append(link["mov_vehs"])
            link["speed_obs"].append(link["speed"])

    def get_agg_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        **kwargs: Any,
    ) -> gpd.GeoDataFrame:
        "Aggregates results to a GeoDataframe"
        if self.df_agg_results is not None:
            return self.df_agg_results

        time_start = time_start if time_start is not None else self.time_start
        time_end = time_end if time_end is not None else self.time_end

        df_aggregated = gpd.GeoDataFrame()
        if self.ass_results is None or len(self.ass_results) == 0:
            self.df_agg_results = None
            return df_aggregated

        col = ["time"] + self.fields
        _n = {
            "time": "time",
            "idx": "id_link",
            "ent_veh": "flow_in",
            "ex_veh": "flow_out",
            "max_que": "max_que",
            "cum_mov_vehs": "mov_vehs",
            "cum_que_vehs": "que_vehs",
            "cum_speed": "speed",
            "cum_density": "density",
            "cum_tt": "tt",
            "n_updates": "n_updates",
            "length": "length",
            "id_link": "id_link",
            "geometry": "geometry",
            "v_max": "v_max",
            "lanes": "lanes",
            "connector": "connector",
            "q_length": "q_length",
        }
        for m in self.modes_codes:
            _n[f"ent_veh_{m}"] = f"flow_in_{m}"
            _n[f"ex_veh_{m}"] = f"flow_out_{m}"

        fields_flow = [_n["ent_veh"], _n["ex_veh"]]
        for m in self.modes_codes:
            fields_flow.append(_n[f"ent_veh_{m}"])
            fields_flow.append(_n[f"ex_veh_{m}"])
        df_aggregated = pd.DataFrame(data=self.ass_results, columns=col).rename(
            columns={n: k for n, k in _n.items() if n in col}
        )
        df_aggregated = df_aggregated.query(f"time >= {time_start} and time <= {time_end}")
        df_aggregated[[_n["cum_mov_vehs"], _n["cum_que_vehs"], _n["cum_speed"], _n["cum_density"], _n["cum_tt"]]] = (
            df_aggregated[
                [_n["cum_mov_vehs"], _n["cum_que_vehs"], _n["cum_speed"], _n["cum_density"], _n["cum_tt"]]
            ].div(df_aggregated[_n["n_updates"]], axis=0)
        )
        df_aggregated[fields_flow] = df_aggregated[fields_flow] * (60 / self.agg_int)

        dtype = {
            _n["idx"]: "Int64",
            _n["ent_veh"]: "Int64",
            _n["ex_veh"]: "Int64",
            _n["max_que"]: "Int64",
            _n["cum_mov_vehs"]: "Float64",
            _n["cum_que_vehs"]: "Float64",
            _n["cum_speed"]: "Float64",
            _n["cum_density"]: "Float64",
            _n["cum_tt"]: "Float64",
            _n["n_updates"]: "Int64",
            _n["time"]: "Int64",  # "datetime64[ns]",
        }
        for m in self.modes_codes:
            dtype[_n[f"ent_veh_{m}"]] = "Int64"
            dtype[_n[f"ex_veh_{m}"]] = "Int64"
        df_aggregated = df_aggregated.astype(dtype)

        result = df_aggregated.drop(columns=[_n["n_updates"]], errors="ignore")
        result = result.dropna(subset=[_n["time"]])

        links_l = pd.DataFrame(
            [
                [
                    link.idx,
                    ST_Multi(link["geometry"]),
                    link["v0"],
                    link["length"],
                    link["lanes"],
                    link["connector"],
                ]
                for link in self.graph.get_all_links()
            ],
            columns=[_n["id_link"], _n["geometry"], _n["v_max"], _n["length"], _n["lanes"], _n["connector"]],
        )
        result = pd.merge(result, links_l, left_on=_n["idx"], right_on=_n["id_link"], suffixes=("", ""))
        result = gpd.GeoDataFrame(result, geometry="geometry", crs=self.ini.GENERAL.CRS_CALC)

        result[_n["cum_speed"]] = result["length"] / result[_n["cum_tt"]] * 60
        result[_n["cum_speed"]] = np.minimum(result[_n["cum_speed"]], result[_n["v_max"]])
        result[_n["max_que"]] = result[_n["max_que"]].clip(lower=0)
        result[_n["q_length"]] = (
            (result[_n["max_que"]] / result[_n["lanes"]])
            * (self.ini.SIMULATOR.CAR_LENGTH / 1000)
            / result[_n["length"]]
            * 100
        )
        result[_n["q_length"]] = result[_n["q_length"]].clip(upper=100)

        final_list = [_n["time"], _n["idx"], _n["ent_veh"], _n["ex_veh"]]
        for m in self.modes_codes:
            final_list.append(_n[f"ent_veh_{m}"])
            final_list.append(_n[f"ex_veh_{m}"])
        final_list.extend(
            [
                _n["max_que"],
                _n["cum_mov_vehs"],
                _n["cum_que_vehs"],
                _n["cum_speed"],
                _n["cum_density"],
                _n["cum_tt"],
                _n["length"],
                _n["v_max"],
                _n["geometry"],
                _n["q_length"],
                _n["connector"],
            ]
        )

        self.df_agg_results = result[final_list]

        return self.df_agg_results

    def get_stats_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame | None:
        "Calculate statistics from the results"
        if self.df_stats_results:
            return self.df_stats_results
        self.get_agg_results(time_start=time_start, time_end=time_end)

        avg_density = "density"
        avg_speed = "speed"
        avg_tt = "tt"
        length = "length"
        v_max = "v_max"
        light_flow_out = "flow_out"
        stats = None

        assert self.df_agg_results is not None, "Aggregated results are not available."
        result_stats = pd.DataFrame(self.df_agg_results.drop(columns="geometry"))
        cong_levels = self.ini.OUTPUT.OUTPUT_CONG_LEVELS
        deltat = self.agg_int / 60

        def f_stat(dat):
            d = {}
            tot_distance = sum(dat[avg_density] * dat.length)
            if tot_distance == 0:
                tot_distance = 1
            d["v_avg"] = sum(dat[avg_density] * dat[avg_speed] * dat[length]) / tot_distance  # velocita' media
            d["p_tot"] = sum(dat[avg_density] * dat[avg_speed] * dat[length] * deltat)  # vehi x km
            d["t_tot"] = sum(dat[avg_density] * dat[length] * deltat)  # Tempo veicoli x km
            for i, v0 in enumerate(cong_levels[:-1]):
                v1 = cong_levels[i + 1]
                mask = (
                    (dat[avg_speed] > v0 * dat[v_max]) & (dat[avg_speed] <= v1 * dat[v_max]) & (dat[light_flow_out] > 0)
                )
                tot_distance = sum(dat[length][dat[light_flow_out] > 0])
                if tot_distance == 0:
                    tot_distance = 1
                perc = sum(dat[length][mask]) / tot_distance
                d[f"cong_{int(v0 * 100)}"] = perc

            mask = (
                (dat[avg_speed] > 0)
                & (dat[avg_speed] <= self.ini.OUTPUT.LOS_CRITICO * dat[v_max])
                & (dat[light_flow_out] > 0)
            )
            d["avg_t_cong"] = len(dat["time"][mask].unique()) * self.agg_int
            d["max_avg_tt"] = dat.groupby("time").sum().max()[avg_tt]
            d["min_avg_tt"] = dat.groupby("time").sum().min()[avg_tt]
            d["arrived"] = sum([1 for veh in self.vehs if veh.status == "arrived"])

            return pd.Series(d)

        monitored_links_sets = self.workspace.monitored_links_sets_model.monitored_links_sets
        links_sets = self.workspace.links_sets_model.links_sets
        segment = {k: v for k, v in links_sets.items() if k in monitored_links_sets}

        stat = []
        for seg, links in segment.items():
            mask = result_stats["id_link"].isin(links)
            if mask.any():
                tmp = f_stat(result_stats[mask])
                tmp["segment_id"] = seg
                stat.append(tmp)
        if stat:
            stats = pd.concat(stat, axis=1).T
            stats.set_index("segment_id", inplace=True)
            stats.reset_index(inplace=True, drop=False)

        self.df_stats_results = stats
        return self.df_stats_results

    def get_trace_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        **kwargs: Any,
    ) -> gpd.GeoDataFrame | None:
        "Get vehicles trace results"

        if self.df_trace_results is not None:
            return self.df_trace_results
        if not self.ind_res:
            return None
        time_start = time_start if time_start is not None else self.time_start
        time_end = time_end if time_end is not None else self.time_end

        # time_start *= 60
        # time_end *= 60
        geo_trace = None

        shape = self.workspace.graph_model.links
        if shape is None:
            self.log.warning("Link GeoDataFrame is not available, converting from graph data.")
            shape = self.workspace.graph_model.to_pandas_links()
        assert shape is not None, "Link GeoDataFrame is not available."
        id_link = "id"
        shape = shape[[id_link, "geometry"]].set_index(id_link)
        tot_data = [v for veh in self.vehs if veh.monitored_veh and veh.trace for v in veh.trace]
        dtype = {"t": float, "p": float, "id_link": int, "status": str, "id": int}
        trace_res: pd.DataFrame | gpd.GeoDataFrame
        if len(tot_data) > 0:
            trace_res = pd.DataFrame(tot_data, columns=["t", "p", "id_link", "status", "id"])
        else:
            trace_res = pd.DataFrame(columns=["t", "p", "id_link", "status", "id"])
        trace_res = trace_res.query("t >= @time_start and t <= @time_end and p <= 1")
        trace_res = trace_res.query("status in ['mov', 'queue']")
        trace_res = trace_res.astype(dtype)
        trace_res = trace_res.join(shape, on="id_link")
        trace_res = gpd.GeoDataFrame(
            data=trace_res.drop(columns="geometry"),
            geometry=trace_res["geometry"],
            crs=shape.crs,
        )

        def angle(geoms, positions, delta=0.01):
            p = positions.to_numpy(dtype=float, na_value=np.nan)

            start = np.clip(p - delta, 0, 1)
            end = np.clip(p + delta, 0, 1)

            a = line_interpolate_point(geoms.array, start, normalized=True)
            b = line_interpolate_point(geoms.array, end, normalized=True)

            dx = get_x(b) - get_x(a)
            dy = get_y(b) - get_y(a)

            az = np.degrees(np.arctan2(dx, dy)) % 360

            # Direzione indefinita se i due punti coincidono.
            az = np.where((dx == 0) & (dy == 0), 0, az)

            return pd.Series(az, index=geoms.index, name="azimuth")

        if trace_res.empty:
            trace_res = trace_res.assign(point=None, rotation=None)
        else:
            trace_res["point"] = trace_res.geometry.interpolate(trace_res["p"], normalized=True)
            trace_res["rotation"] = angle(trace_res.geometry, trace_res["p"])
        geo_trace = gpd.GeoDataFrame(
            data=trace_res[["t", "id", "id_link", "status", "p", "rotation"]],
            geometry=trace_res["point"],
            crs=shape.crs,
        )
        dtype = {"t": float, "id": int, "id_link": int, "status": str, "p": float, "rotation": float}
        geo_trace = geo_trace.astype(dtype)
        self.df_trace_results = geo_trace

        return self.df_trace_results

    def get_signalized_results(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        **kwargs: Any,
    ) -> gpd.GeoDataFrame | None:
        if self.df_signalized_results is not None:
            return self.df_signalized_results

        time_start = time_start if time_start is not None else self.time_start
        time_end = time_end if time_end is not None else self.time_end

        "Get signalized nodes results"
        sign_res = pd.DataFrame(columns=["id_from", "id_to", "t", "type", "status"]).astype(
            {"id_from": int, "id_to": int, "t": int, "type": str, "status": str}
        )

        if self.signalized_nodes:
            for node in self.signalized_nodes:
                sig_res = pd.DataFrame(data=node.res, columns=sign_res.columns)
                sign_res = pd.concat([sign_res, sig_res], axis=0)

            sign_res.columns = ["id_from", "id_to", "t", "type", "status"]

            shape = self.workspace.graph_model.links
            if shape is None or shape.empty:
                self.log.warning("Link GeoDataFrame is not available, converting from graph data.")
                shape = self.workspace.graph_model.to_pandas_links()
            assert shape is not None, "Link GeoDataFrame is not available."
            id_link = "id"
            shape = shape[[id_link, "geometry"]].rename(columns={id_link: "id_from"}).set_index("id_from")
            sign_res = shape.merge(sign_res, right_on="id_from", left_index=True)
            self.df_signalized_results = sign_res
            return self.df_signalized_results
        return None
