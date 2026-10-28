"""Time dependent shortest path computation, optionally run in parallel."""

from __future__ import annotations

import time
from typing import Any, Generator

from graph import KPathList

from ..base.base_algorithm import BaseAlgorithm
from ..database import Execution
from ..model.graph_model import GraphBase, TimeDependentLinkBasedShortestPath
from ..model.modes_model import ModesType
from ..model.paths_model import MultimodalPathsType, PathsModel


class ShortestPath(BaseAlgorithm):
    """Compute time dependent shortest paths for every mode and timestamp."""

    def __init__(
        self,
        use_parallel: bool | None = None,
        n_workers: float | None = None,
        execution: Execution | None = None,
        **kwargs,
    ):
        """Build the algorithm and select the execution strategy.

        Args:
            app: Running AMISim application.
            parallel: If `True`, `run` distributes the tasks on `app.parallel`.
            **kwargs: Extra arguments forwarded to the base class.
        """
        super().__init__(execution=execution, **kwargs)
        self.use_parallel: bool = use_parallel if use_parallel is not None else True
        self.n_workers: float | None = n_workers if n_workers is not None else self.app.ini.ASSIGNMENT.SPP_NUM_CPUS
        self.paths: MultimodalPathsType | None = None
        self.graph: GraphBase | None = None
        self.nodes: list[int] | None = None
        self.timestamps: list[int] | None = None
        self.modes: ModesType | None = None
        self.node_mode_field: str = "modes"
        self.link_mode_field: str = "modes"
        self.turn_mode_field: str = "modes"
        self.node_cost_field: str = "time"
        self.link_cost_field: str = "time"
        self.turn_cost_field: str = "time"
        self.turn_prohibited_field: str = "prohibited"

    def init(
        self,
        graph: GraphBase | None = None,
        nodes: list[int] | None = None,
        modes: ModesType | None = None,
        timestamps: list[int] | None = None,
        node_mode_field: str | None = None,
        link_mode_field: str | None = None,
        turn_mode_field: str | None = None,
        node_cost_field: str | None = None,
        link_cost_field: str | None = None,
        turn_cost_field: str | None = None,
        turn_prohibited_field: str | None = None,
        **kwargs: Any,
    ) -> ShortestPath:
        if graph is not None:
            self.graph = graph
        if nodes is not None:
            self.nodes = nodes
        if modes is not None:
            self.modes = modes
        if timestamps is not None:
            self.timestamps = timestamps
        if node_mode_field is not None:
            self.node_mode_field = node_mode_field
        if link_mode_field is not None:
            self.link_mode_field = link_mode_field
        if turn_mode_field is not None:
            self.turn_mode_field = turn_mode_field
        if node_cost_field is not None:
            self.node_cost_field = node_cost_field
        if link_cost_field is not None:
            self.link_cost_field = link_cost_field
        if turn_cost_field is not None:
            self.turn_cost_field = turn_cost_field
        if turn_prohibited_field is not None:
            self.turn_prohibited_field = turn_prohibited_field
        return self

    def update(
        self,
        graph: GraphBase | None = None,
        nodes: list[int] | None = None,
        modes: ModesType | None = None,
        timestamps: list[int] | None = None,
        node_mode_field: str | None = None,
        link_mode_field: str | None = None,
        turn_mode_field: str | None = None,
        node_cost_field: str | None = None,
        link_cost_field: str | None = None,
        turn_cost_field: str | None = None,
        turn_prohibited_field: str | None = None,
        **kwargs: Any,
    ) -> ShortestPath:
        if graph is not None:
            self.graph = graph
        if nodes is not None:
            self.nodes = nodes
        if modes is not None:
            self.modes = modes
        if timestamps is not None:
            self.timestamps = timestamps
        if node_mode_field is not None:
            self.node_mode_field = node_mode_field
        if link_mode_field is not None:
            self.link_mode_field = link_mode_field
        if turn_mode_field is not None:
            self.turn_mode_field = turn_mode_field
        if node_cost_field is not None:
            self.node_cost_field = node_cost_field
        if link_cost_field is not None:
            self.link_cost_field = link_cost_field
        if turn_cost_field is not None:
            self.turn_cost_field = turn_cost_field
        if turn_prohibited_field is not None:
            self.turn_prohibited_field = turn_prohibited_field
        return self

    def run(
        self,
        graph: GraphBase | None = None,
        nodes: list[int] | None = None,
        modes: ModesType | None = None,
        timestamps: list[int] | None = None,
        node_mode_field: str = "modes",
        link_mode_field: str = "modes",
        turn_mode_field: str = "modes",
        node_cost_field: str = "time",
        link_cost_field: str = "time",
        turn_cost_field: str = "time",
        turn_prohibited_field: str = "prohibited",
        **kwargs: Any,
    ) -> PathsModel:
        """Compute the shortest paths between the requested nodes.

        Args:
            graph: Graph to route on; defaults to the workspace graph.
            nodes: Origin and destination nodes; defaults to the graph centroids.
            modes: Modes to process; defaults to the workspace modes.
            timestamps: Departure timestamps; defaults to the graph timestamps.
            node_mode_field: Node attribute holding the allowed modes.
            link_mode_fields: Link attribute holding the allowed modes.
            turn_mode_field: Turn attribute holding the allowed modes.
            node_cost_field: Node attribute holding the cost.
            link_cost_field: Link attribute holding the cost.
            turn_cost_field: Turn attribute holding the cost.
            turn_prohibited_field: Turn attribute flagging prohibited turns.

        Returns:
            The computed paths grouped by mode.
        """
        assert self.app is not None, "App must be available"
        assert self.app.workspace is not None, "Workspace must be available"
        self.graph = (
            graph or self.graph or (self.app.workspace.graph_model.graph if self.app.workspace.graph_model else None)
        )
        assert self.graph is not None, "Graph must be provided or available in the workspace"
        self.nodes = (
            nodes
            or self.nodes
            or (self.app.workspace.graph_model.centroids if self.app.workspace.graph_model else None)
        )
        assert self.nodes is not None, "Nodes must be provided or centroids available in the graph"
        self.modes = (
            modes or self.modes or (self.app.workspace.modes_model.modes if self.app.workspace.modes_model else None)
        )
        assert self.modes is not None, "Modes must be provided or available in the workspace"
        self.timestamps = (
            timestamps
            or self.timestamps
            or (self.app.workspace.graph_model.get_t_starts() if self.app.workspace.graph_model else None)
        )
        assert self.timestamps is not None, "Timestamps must be provided or available in the graph or workspace"
        self.node_mode_field = node_mode_field or self.node_mode_field or "modes"
        self.turn_mode_field = turn_mode_field or self.turn_mode_field or "modes"
        self.link_mode_field = link_mode_field or self.link_mode_field or "modes"
        self.node_cost_field = node_cost_field or self.node_cost_field or "time"
        self.link_cost_field = link_cost_field or self.link_cost_field or "time"
        self.turn_cost_field = turn_cost_field or self.turn_cost_field or "time"
        self.turn_prohibited_field = turn_prohibited_field or self.turn_prohibited_field or "prohibited"
        fields = {
            "node_mode_field": self.node_mode_field,
            "turn_mode_field": self.turn_mode_field,
            "link_mode_field": self.link_mode_field,
            "node_cost_field": self.node_cost_field,
            "link_cost_field": self.link_cost_field,
            "turn_cost_field": self.turn_cost_field,
            "turn_prohibited_field": self.turn_prohibited_field,
        }
        t_start = time.time()
        if self.use_parallel:
            ret = self._run_parallel(self.graph, self.nodes, self.modes, self.timestamps, fields)
        else:
            self.log.debug("Running shortest path algorithm")
            mm_paths = MultimodalPathsType()
            for mode in self.modes if self.modes is not None else []:
                self.log.debug(f"Processing mode: {mode}")
                paths = mm_paths.get_by_mode(mode, create_if_missing=True)
                if paths is None:
                    continue
                router = TimeDependentLinkBasedShortestPath.from_graph(
                    graph=self.graph,
                    mode=mode,
                    **fields,
                )
                for timestamp in self.timestamps:
                    self.log.debug(f"Processing timestamp: {timestamp}")
                    nodes_set = set(self.nodes)
                    for origin in nodes_set:
                        targets = nodes_set - {origin}
                        _paths = router.shortest_paths(source=origin, targets=targets, t_start=timestamp)
                        if _paths is not None:
                            paths.merge(_paths)
            self.paths = mm_paths
            ret = PathsModel(paths=mm_paths)
        self.log.debug(f"Path calculated in: {(time.time() - t_start):.2f} seconds")
        return ret

    def _run_parallel(
        self,
        graph: GraphBase,
        nodes: list[int],
        modes: ModesType,
        timestamps: list[int],
        fields: dict[str, str],
    ) -> PathsModel:
        """Compute the shortest paths distributing the tasks on the application runtime."""
        tasks = list(get_tasks(nodes=nodes, modes=modes, timestamps=timestamps))
        self.log.debug(f"Running shortest path algorithm in parallel on {len(tasks)} tasks")
        mm_paths: MultimodalPathsType = MultimodalPathsType()
        for chunk_results in self.app.parallel.map(
            fn=calculate_paths, tasks=tasks, graph=graph, fields=fields, n_workers=self.n_workers
        ):
            for mode, chunk_paths in chunk_results.items():
                paths = mm_paths.get_by_mode(mode, create_if_missing=True)
                if paths is not None:
                    paths.merge(chunk_paths)
        return PathsModel(paths=mm_paths)


def calculate_paths(tasks: list[dict[str, Any]], graph: Any, fields: dict[str, str]) -> dict[str, KPathList]:
    """Solve a chunk of shortest path tasks reusing one router per mode.

    Args:
        tasks: Task dictionaries produced by `get_tasks`.
        graph: Graph the routers are built from.
        fields: Field names forwarded to the router factory.

    Returns:
        Mapping from mode to the paths computed for that mode.
    """
    routers: dict[str, TimeDependentLinkBasedShortestPath] = {}
    results: dict[str, KPathList] = {}
    for task in tasks:
        mode = task["mode"]
        router = routers.get(mode)
        if router is None:
            router = TimeDependentLinkBasedShortestPath.from_graph(graph=graph, mode=mode, **fields)
            routers[mode] = router
            results[mode] = KPathList()
        _paths = router.shortest_paths(
            source=task["origin"],
            targets=task["targets"],
            t_start=task["timestamp"],
        )
        if _paths is not None:
            results[mode].merge(_paths)
    return results


def get_tasks(nodes: list[int], modes: ModesType, timestamps: list[int]) -> Generator[dict[str, Any], None, None]:
    """Yield one shortest path task per mode, timestamp and origin node.

    Args:
        nodes: Candidate origin and destination nodes.
        modes: Modes to compute the paths for.
        timestamps: Departure timestamps.

    Yields:
        Task dictionaries with `origin`, `targets`, `mode` and `timestamp`.
    """
    unique_nodes = list(dict.fromkeys(nodes))
    for mode in modes if modes is not None else []:
        for timestamp in timestamps:
            for index, origin in enumerate(unique_nodes):
                yield {
                    "origin": origin,
                    "targets": unique_nodes[:index] + unique_nodes[index + 1 :],
                    "mode": mode,
                    "timestamp": timestamp,
                }


__all__ = ["ShortestPath"]
