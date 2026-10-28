# -*- coding: utf-8 -*-
"""
Created on Fri Oct  1 17:32:40 2021

@author: Natalia
"""

from __future__ import annotations

from typing import Hashable

import numpy as np
from numba import njit

from ...config.ini_model import IniModel
from ...model.graph_model import GraphBase
from ...model.modes_model import ModeCode
from ...model.paths_model import PathType

transfer_condition = {"mov", "queue", "arrived", "sleeping"}
node_conditions = {"queueing", "at node"}


class Car:
    ini: IniModel
    ind_res: bool
    mon_veh: int
    rng: np.random.Generator
    lt1: float
    lt2: float

    def __init__(self, id_n: int, t: float, path: PathType, G: GraphBase, deltat: float, mode: ModeCode):
        self.deltat = deltat
        self.ID = id_n  # vehicle ID
        self.path_links: list[Hashable] = path["links"]  # path of vehicle
        self.ent_time: float = t  # [m] entrance on the network
        self.status: str = "sleeping"  # status of vehicle
        self.G: GraphBase = G  # graph
        self.signalized_links: list = G["signalized_links"]
        self.o: Hashable = path["source"]
        self.d: Hashable = path["target"]

        self.signalized_turns: dict = G["signalized_turns"]

        self.c_l: int = 0  # current link
        self.n_l: int = 1  # next link
        self.s_t: float | None = None
        self.same_link: bool = False

        if self.ind_res:
            self.monitored_veh = Car.rng.random() < Car.mon_veh / 100
        else:
            self.monitored_veh = False
        self.trace: list[tuple] = []

        self.current_link = self.G.get_link_or_error(self.path_links[self.c_l])
        self.next_link = self.G.get_link_or_error(self.path_links[self.n_l])
        self.last_link = self.G.get_link_or_error(self.path_links[-1])

        self.current_link["mov_vehs"] += 1  # type: ignore # add one vehicle on the current link link

        self.c_l_ti: float = self.ent_time  # [m] entrance time on current link
        self.c_l_tf: float = 0  # [m] exit time on current link

        self.mode = mode
        self.field_ent_m = f"ent_veh_{mode}"
        self.field_out_m = f"ex_veh_{mode}"

        self.field_ent = "ent_veh"
        self.field_out = "ex_veh"

        self.current_link[self.field_ent] += 1  # type: ignore
        self.current_link[self.field_ent_m] += 1  # type: ignore

        self.critical_gap = 5 / 3600

    def update_graph(self, graph: GraphBase):
        self.G = graph
        self.current_link = self.G.get_link_or_error(self.path_links[self.c_l])
        self.last_link = self.G.get_link_or_error(self.path_links[-1])
        if self.status == "sleeping":
            self.current_link["mov_vehs"] += 1  # type: ignore # add one vehicle on the current link link
            self.current_link[self.field_ent] += 1  # type: ignore
            self.current_link[self.field_ent_m] += 1  # type: ignore

    def link_transfer(self, t):

        tt = t + self.deltat
        dt: float = self.c_l_tf - self.c_l_ti

        if dt == 0:
            s_t = 1
        else:
            s_t = (tt - self.c_l_ti) / dt  # space traveled on link

        self.tt = tt
        self.s_t = s_t
        free_link = 1 - self.current_link["l_queue"] / self.current_link["length"]  # type: ignore # space link free of queue

        if (self.c_l_tf > tt) & (s_t < free_link):  # still traveling
            self.status = "mov"
            self.current_link["storage_cap"] -= 1 - self.current_link["ksi"]  # type: ignore
            self.same_link = True

        elif (self.c_l_tf <= tt) & (s_t >= free_link):  # should exit
            self.status = "at node"
            self.current_link["mov_vehs"] -= 1  # type: ignore
            self.current_link["que_vehs"] += 1  # type: ignore

        elif (self.c_l_tf > tt) & (
            s_t >= free_link
        ):  # encountred queue but would not have exited, need to update exit time
            self.status = "queueing"
            self.c_l_tf = max(tt + self.deltat, free_link * (self.c_l_tf - self.c_l_ti) + self.c_l_ti)
            self.current_link["mov_vehs"] -= 1
            self.current_link["que_vehs"] += 1
            self.current_link["storage_cap"] -= 1 - self.current_link["ksi"]
            self.same_link = True

    def numba_link_transfer(self, t: float):
        vars = self._numba_link_transfer(
            t,
            self.deltat,
            self.c_l_tf,
            self.c_l_ti,
            self.current_link["l_queue"],  # type: ignore
            self.current_link["length"],  # type: ignore
            self.status,
            self.current_link["storage_cap"],  # type: ignore
            self.current_link["ksi"],  # type: ignore
            self.current_link["mov_vehs"],  # type: ignore
            self.current_link["que_vehs"],  # type: ignore
            self.same_link,
        )
        (
            self.deltat,
            self.c_l_tf,
            self.c_l_ti,
            self.tt,
            self.s_t,
            self.current_link["l_queue"],
            self.current_link["length"],
            self.status,
            self.current_link["storage_cap"],
            self.current_link["ksi"],
            self.current_link["mov_vehs"],
            self.current_link["que_vehs"],
            self.same_link,
        ) = vars

    @staticmethod
    @njit
    def _numba_link_transfer(
        t: float,
        self_deltat: float,
        self_c_l_tf: float,
        self_c_l_ti: float,
        self_current_link_l_queue: float,
        self_current_link_length: float,
        self_status: str,
        self_current_link_storage_cap: int,
        self_current_link_ksi: int,
        self_current_link_mov_vehs: int,
        self_current_link_que_vehs: int,
        self_same_link: bool,
    ):
        tt = t + self_deltat
        dt: float = self_c_l_tf - self_c_l_ti

        s_t = 0.0
        if abs(dt) < 1e-3:
            s_t = 1.0
        else:
            s_t = (tt - self_c_l_ti) / dt  # space traveled on link

        self_tt = tt
        self_s_t = s_t
        free_link = 1 - self_current_link_l_queue / self_current_link_length  # type: ignore # space link free of queue

        if (self_c_l_tf > tt) and (s_t < free_link):  # still traveling
            self_status = "mov"
            self_current_link_storage_cap -= 1 - self_current_link_ksi  # type: ignore
            self_same_link = True

        elif (self_c_l_tf <= tt) and (s_t >= free_link):  # should exit
            self_status = "at node"
            self_current_link_mov_vehs -= 1
            self_current_link_que_vehs += 1

        elif (self_c_l_tf > tt) and (
            s_t >= free_link
        ):  # encountred queue but would not have exited, need to update exit time
            self_status = "queueing"
            self_c_l_tf = max(tt + self_deltat, free_link * (self_c_l_tf - self_c_l_ti) + self_c_l_ti)
            self_current_link_mov_vehs -= 1
            self_current_link_que_vehs += 1
            self_current_link_storage_cap -= 1 - self_current_link_ksi
            self_same_link = True
        return (
            self_deltat,
            self_c_l_tf,
            self_c_l_ti,
            self_tt,
            self_s_t,
            self_current_link_l_queue,
            self_current_link_length,
            self_status,
            self_current_link_storage_cap,
            self_current_link_ksi,
            self_current_link_mov_vehs,
            self_current_link_que_vehs,
            self_same_link,
        )

    def node_transfer(self, t):
        permitted_turn = True
        # if self.status in node_conditions: #  implementato a livello superiore per evitare la chiamata
        if self.status == "queueing":  # if it just encountred the queue, update exit time and put it as queuing vehicle
            self.status = "queue"

        else:  # the vehicle arrived to a node and needs to check capacity constraints
            if self.current_link is self.last_link:  # arrived at the end of the last link
                self.status = "arrived"
                self.current_link["que_vehs"] -= 1
                self.current_link["storage_cap"] += 1

            else:
                self.next_link = self.G.get_link_or_error(self.path_links[self.n_l])  # assign new next link

                l = self.current_link["idx"]
                nl = self.next_link["idx"]

                try:
                    nnl = None if self.n_l + 1 >= len(self.path_links) else self.path_links[self.n_l + 1]
                except:
                    nnl = None

                if l in self.signalized_links:
                    key: tuple[Hashable, Hashable] | tuple[Hashable, Hashable, Hashable] | None = (
                        (l, nl) if (l, nl) in self.signalized_turns else None
                    )
                    key = (l, nl, nnl) if (l, nl, nnl) in self.signalized_turns else key

                    if key:
                        permitted_turn = self.signalized_turns[key]["state"] == "green"
                        # pdb.set_trace()

                        if self.signalized_turns[key]["type"] == "left_turn":
                            if self.signalized_turns[key]["permitted"] & permitted_turn:
                                # pdb.set_trace()

                                fl = self.G["signalized_turns"][key]["opposite_turn"]["from_link"]
                                fl = self.G.get_link_or_error(fl)  # match opposite direction
                                mv = fl["mov_vehs"]

                                if mv > 0:
                                    dmv = fl["length"] / (fl["mov_vehs"] * fl["speed"])
                                else:
                                    dmv = 100000

                                if dmv > self.critical_gap or self.signalized_turns[key]["permitted_movs"] == 0:
                                    permitted_turn = False

                if (
                    (self.current_link["inflow_cap"] >= 1) & (self.next_link["storage_cap"] >= 1) & permitted_turn
                ):  # capacity of next link and on current link
                    self.update_cap(self.current_link, self.next_link)

                    ex = self.current_link["ex_q_veh"]
                    if ex:
                        lost_time = self.lt1 + ex * self.lt2
                    else:
                        lost_time = 0

                    if self.current_link["l_queue"]:
                        self.current_link["ex_q_veh"] += 1

                    self.status = "moving"  # transfer the vehicle on next link, update the capacities, detectors, enter and exit time and counter of the vehicles on next link
                    self.c_l_ti = self.c_l_tf + lost_time
                    self.c_l_tf = self.c_l_ti + self.next_link["ta"]
                    self.c_l += 1
                    self.n_l += 1
                    self.current_link = self.G.get_link_or_error(self.path_links[self.c_l])

                else:
                    self.status = "queue"  # put vehicle as a queuing vehicle and update its exit time (CHECK THIS!!!.)
                    self.c_l_tf = t + self.deltat
                    if self.same_link:
                        pass
                    else:
                        self.current_link["storage_cap"] -= 1 - self.current_link["ksi"]
                        self.same_link = True

    def move(self, t):

        if self.status == "arrived" and not self.monitored_veh:
            return False

        if self.status == "sleeping":
            if t >= self.ent_time:
                self.status = "moving"
                self.c_l_tf = self.c_l_ti + self.current_link["ta"]  # exit time on current link

        test = 0
        while self.status not in transfer_condition:
            test += 1
            if test == 1000:
                print(
                    "Vehicle locked",
                    str(self.ID),
                    self.status,
                    self.current_link["idx"],
                    self.next_link["idx"],
                )
            if self.status == "moving":
                self.link_transfer(t)
            if self.status in node_conditions:
                self.node_transfer(t)
        if test >= 1000:
            print("Vehicle unlocked", test)

        if self.monitored_veh:
            ss = self.s_t if self.s_t else 0
            self.trace.append((t, ss, self.current_link["idx"], self.status, self.ID))

        if self.status == "mov":
            self.status = "moving"
        elif self.status == "queue":
            self.status = "at node"

        return self.status != "arrived" if not self.monitored_veh else True

    def update_cap(self, current_link, next_link):
        # update variable when transfering from current link to next link
        current_link["que_vehs"] -= 1
        current_link["inflow_cap"] -= 1

        ksi = 1 if self.same_link else current_link["ksi"]

        current_link["storage_cap"] += ksi

        current_link[self.field_out] += 1
        current_link[self.field_out_m] += 1

        next_link[self.field_ent] += 1
        next_link[self.field_ent_m] += 1

        next_link["mov_vehs"] += 1
        next_link["storage_cap"] -= next_link["ksi"]

        self.same_link = False
