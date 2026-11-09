"""Link-based, time-dependent shortest-path routing.

The :class:`TimeDependentLinkBasedShortestPath` router is a routing-only view of
``Graph``. Nodes and links are converted to dense integer indices, while the
original hashable identifiers stay at the public API boundary.

Costs are interpreted as durations and must use the same time unit as
``Graph.delta_t`` and ``departure_time``. A vector cost is piecewise constant:
element ``k`` applies on ``[k * delta_t, (k + 1) * delta_t)`` relative to
``Graph.t0``.

The shortest-path method implements link-based time-dependent Dijkstra. It is
correct for FIFO cost functions; waiting at nodes is not modelled.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable
from heapq import heappop as pop
from heapq import heappush as push
from itertools import count
from typing import Any, cast

from ..graphs.graph import Graph
from ..graphs.link import Link
from ..graphs.node import Node
from ..graphs.turn import Turn
from ..paths import Path, PathContainer, PathList
from ..utils import time_index

CostProfile = tuple[float, ...]
NodeRow = tuple[int, Hashable, CostProfile]
LinkRow = tuple[int, Hashable, int, int, CostProfile]
TurnRow = tuple[int, Hashable, int, int, CostProfile]


class TimeDependentLinkBasedShortestPath:
    """Compute link-based shortest paths on a time-dependent graph."""

    def __init__(self) -> None:
        """Create an empty router. Use ``from_graph`` to populate it."""
        self.delta_t: int | float = 1
        self.total_time: int | float = 10
        self.n_intervals: int = 0
        self.t0: int | float = 0
        self.mode: str | None = None
        self.nodes: tuple[NodeRow, ...] = tuple()
        self.links: tuple[LinkRow, ...] = tuple()
        self.turns: dict[tuple[int, int], set[TurnRow]] = {}
        self.turns_prohibited: set[tuple[int, int]] = set()
        self.fws: dict[int, set[LinkRow]] = {}
        self.links_fws: dict[int, set[LinkRow]] = {}
        self.n_nodes: int = 0
        self.n_links: int = 0
        self.n_turns: int = 0
        self._nodes_idx: dict[Hashable, int] = {}
        self._links_idx: dict[Hashable, int] = {}

    @staticmethod
    def from_graph(
        graph: Graph,
        mode: str | None = None,
        link_mode_field: str | None = None,
        node_mode_field: str | None = None,
        turn_mode_field: str | None = None,
        link_cost_field: str | None = None,
        node_cost_field: str | None = None,
        turn_cost_field: str | None = None,
        turn_prohibited_field: str | None = None,
    ) -> TimeDependentLinkBasedShortestPath:
        """Build a router from a ``Graph`` instance."""
        router = TimeDependentLinkBasedShortestPath()
        router.delta_t = graph.delta_t
        router.total_time = graph.total_time
        router.t0 = graph.t0
        router.n_intervals = int(graph.num_intervals)
        router.mode = mode

        def has_mode(element: Node | Link | Turn, field: str | None) -> bool:
            """Has mode.

            Args:
                element: TODO describe element.
                field: TODO describe field.

            Returns:
                TODO describe return value.

            """
            if mode is None or field is None:
                return True
            available_modes = element.get(field)
            if available_modes is None:
                return True
            if isinstance(available_modes, str):
                available_modes = {available_modes}
            return "all" in available_modes or mode in available_modes

        def expand_cost(
            element: Node | Link | Turn,
            field: str | None,
            default: float | int = 0,
        ) -> CostProfile:
            """Expand cost.

            Args:
                element: TODO describe element.
                field: TODO describe field.
                default: TODO describe default.

            Returns:
                TODO describe return value.

            """
            if field is None or field not in element:
                return tuple([float(default)] * router.n_intervals)

            value = element.get(field)
            if value is None:
                return tuple([float(default)] * router.n_intervals)
            if isinstance(value, int | float | str):
                return tuple([float(value)] * router.n_intervals)

            try:
                values = tuple(float(item) for item in value)
            except TypeError:
                return tuple([float(value)] * router.n_intervals)

            if not values:
                return tuple([float(default)] * router.n_intervals)
            if len(values) < router.n_intervals:
                values = values + tuple([values[-1]] * (router.n_intervals - len(values)))
            return values[: router.n_intervals]

        def is_turn_prohibited(turn: Turn) -> bool:
            """Is turn prohibited.

            Args:
                turn: TODO describe turn.

            Returns:
                TODO describe return value.

            """
            if turn_prohibited_field is None:
                return False
            return bool(turn.get(turn_prohibited_field, False))

        node_data = (
            (node.idx, expand_cost(node, node_cost_field))
            for node in graph.get_all_nodes()
            if has_mode(node, node_mode_field)
        )
        router.nodes = tuple((dense_id, *node) for dense_id, node in enumerate(node_data))
        router._nodes_idx = {node[1]: dense_id for dense_id, node in enumerate(router.nodes)}

        link_data = (
            (
                link.idx,
                router._nodes_idx[link.i],
                router._nodes_idx[link.j],
                expand_cost(link, link_cost_field),
            )
            for link in graph.get_all_links()
            if link.i in router._nodes_idx and link.j in router._nodes_idx and has_mode(link, link_mode_field)
        )
        router.links = tuple((dense_id, *link) for dense_id, link in enumerate(link_data))
        router._links_idx = {link[1]: dense_id for dense_id, link in enumerate(router.links)}

        turn_rows: list[TurnRow] = []
        prohibited_pairs: set[tuple[int, int]] = set()
        for turn in graph.get_all_turns():
            if (
                turn.in_link not in router._links_idx
                or turn.out_link not in router._links_idx
                or not has_mode(turn, turn_mode_field)
            ):
                continue

            pair = (router._links_idx[turn.in_link], router._links_idx[turn.out_link])
            if is_turn_prohibited(turn):
                prohibited_pairs.add(pair)
                continue

            turn_rows.append(
                (
                    len(turn_rows),
                    turn.idx,
                    pair[0],
                    pair[1],
                    expand_cost(turn, turn_cost_field),
                )
            )

        turns_by_pair: defaultdict[tuple[int, int], set[TurnRow]] = defaultdict(set)
        for turn_row in turn_rows:
            turns_by_pair[(turn_row[2], turn_row[3])].add(turn_row)

        router.turns = dict(turns_by_pair)
        router.turns_prohibited = prohibited_pairs
        router.n_nodes = len(router.nodes)
        router.n_links = len(router.links)
        router.n_turns = len(turn_rows)

        fws: defaultdict[int, set[LinkRow]] = defaultdict(set)
        for link in router.links:
            fws[link[2]].add(link)
        router.fws = dict(fws)

        links_fws: dict[int, set[LinkRow]] = {}
        for link in router.links:
            links_fws[link[0]] = set(fws.get(link[3], set())) - {link}

        for incoming_link_id, outgoing_link_id in router.turns_prohibited:
            if incoming_link_id in links_fws:
                links_fws[incoming_link_id] = {
                    link for link in links_fws[incoming_link_id] if link[0] != outgoing_link_id
                }
        router.links_fws = links_fws

        return router

    def shortest_paths(
        self,
        source: Node | Hashable,
        targets: Iterable[Hashable] | Hashable | None = None,
        t_start: int | float = 0,
        **kwargs: Any,
    ) -> PathContainer:
        """Compute shortest paths from ``source`` to one or more targets."""
        del kwargs
        source_label = source.idx if isinstance(source, Node) else source
        source_id = self._nodes_idx[source_label]

        target_labels = self._normalize_targets(targets)
        target_ids = {self._nodes_idx[target] for target in target_labels}
        residual_targets = target_ids.copy()

        paths = PathList()
        paths_links: list[list[Hashable]] = [[] for _ in self.links]
        paths_costs = [float("inf")] * self.n_links
        best_target_link: dict[int, int] = {}

        queue: list[tuple[float, int, LinkRow]] = []
        tie_breaker = count()
        departure_time = self.t0 + t_start

        for start_link in self.fws.get(source_id, set()):
            start_link_id, start_link_idx, _, _, link_costs = start_link
            cost_index = time_index(
                t0=self.t0, delta_t=self.delta_t, n_intervals=self.n_intervals, time_value=departure_time
            )
            arrival_time = departure_time + link_costs[cost_index]
            paths_costs[start_link_id] = arrival_time
            paths_links[start_link_id] = [start_link_idx]
            push(queue, (arrival_time, next(tie_breaker), start_link))

        while queue:
            current_time, _, incoming_link = pop(queue)
            incoming_link_id, _, _, current_node, _ = incoming_link

            if current_time > paths_costs[incoming_link_id]:
                continue

            if current_node in residual_targets:
                best_target_link[current_node] = incoming_link_id
                residual_targets.discard(current_node)
                if not residual_targets:
                    break

            for outgoing_link in self.links_fws.get(incoming_link_id, set()):
                outgoing_link_id, outgoing_link_idx, _, _, outgoing_link_costs = outgoing_link
                cost_index = time_index(
                    t0=self.t0, delta_t=self.delta_t, n_intervals=self.n_intervals, time_value=current_time
                )
                node_costs = self.nodes[current_node][2]
                transition_cost = node_costs[cost_index]
                if transition_cost == float("inf"):
                    continue

                for turn in self.turns.get((incoming_link_id, outgoing_link_id), set()):
                    transition_cost += turn[4][cost_index]
                if transition_cost == float("inf"):
                    continue

                outgoing_departure_time = current_time + transition_cost
                link_cost_index = time_index(
                    t0=self.t0, delta_t=self.delta_t, n_intervals=self.n_intervals, time_value=outgoing_departure_time
                )
                candidate_time = outgoing_departure_time + outgoing_link_costs[link_cost_index]

                if candidate_time < paths_costs[outgoing_link_id]:
                    paths_costs[outgoing_link_id] = candidate_time
                    paths_links[outgoing_link_id] = paths_links[incoming_link_id] + [outgoing_link_idx]
                    push(queue, (candidate_time, next(tie_breaker), outgoing_link))

        for target_id in target_ids:
            last_link_id = best_target_link.get(target_id)
            if last_link_id is None:
                continue
            link_ids = paths_links[last_link_id]
            path_costs = [paths_costs[self._links_idx[link_id]] for link_id in link_ids]
            paths.add_path(
                Path(
                    source=cast(int, source_label),
                    target=cast(int, self.nodes[target_id][1]),
                    t_start=int(t_start),
                    links=cast("list[int]", link_ids),
                    costs=path_costs,
                    mode=self.mode,
                    t_base=int(self.t0),
                )
            )

        return paths

    def _normalize_targets(
        self,
        targets: Iterable[Hashable] | Hashable | None,
    ) -> set[Hashable]:
        # Internal helper: normalize targets.
        """Internal helper: normalize targets."""
        if targets is None:
            return {node[1] for node in self.nodes}
        try:
            if targets in self._nodes_idx:
                return {targets}
        except TypeError:
            pass
        if isinstance(targets, Iterable) and not isinstance(targets, str | bytes):
            return set(cast(Iterable[Hashable], targets))
        return {targets}


__all__ = ["TimeDependentLinkBasedShortestPath"]
