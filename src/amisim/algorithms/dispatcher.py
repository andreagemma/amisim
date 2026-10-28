"""Dispatch of the algorithm operations exposed by the application."""

from __future__ import annotations

from ..model.graph_model import GraphModel
from ..model.modes_model import ModesModel
from ..model.paths_model import PathsModel
from .shortest_path import ShortestPath

__all__ = ["Dispatcher", "DispatcherOperation"]


class DispatcherOperation:
    """Names of the operations the dispatcher can execute."""

    SHORTEST_PATH = "shortest_path"

    @classmethod
    def parse(cls, operation: str) -> DispatcherOperation:
        """Return the operation matching `operation`.

        Args:
            operation: Operation name to resolve.

        Returns:
            The matching operation constant.

        Raises:
            ValueError: If the name does not match any known operation.
        """
        for attr in dir(cls):
            if not attr.startswith("__") and getattr(cls, attr) == operation:
                return getattr(cls, attr)
        raise ValueError(f"Unknown operation: {operation}")


class Dispatcher:
    """Run the algorithms of the application by operation name."""

    def __init__(self, app):
        """Store the application instance used to run the algorithms.

        Args:
            app: Running `AmisimApp` instance.

        Raises:
            TypeError: If `app` is not an `AmisimApp` instance.
        """
        from ..amisim_app import AmisimApp

        if not isinstance(app, AmisimApp):
            raise TypeError(f"Expected AmisimApp instance, got {type(app)}")
        self.app = app

    def dispatch(self, operation: str | DispatcherOperation):
        """Execute the algorithm bound to `operation`.

        Args:
            operation: Operation name or constant to execute.

        Raises:
            ValueError: If the operation is not supported.
        """
        if isinstance(operation, str):
            operation = DispatcherOperation.parse(operation)
        if operation == DispatcherOperation.SHORTEST_PATH:
            self.shortest_path()
        else:
            raise ValueError(f"Unknown operation: {operation}")

    def shortest_path(
        self,
        graph: GraphModel | None = None,
        nodes: list[int] | None = None,
        modes: ModesModel | None = None,
        timestamps: list[int] | None = None,
        node_mode_field: str = "modes",
        link_mode_fields: str = "modes",
        turn_mode_field: str = "modes",
        node_cost_field: str = "time",
        link_cost_field: str = "time",
        turn_cost_field: str = "time",
        turn_prohibited_field: str = "prohibited",
        **kwargs,
    ) -> PathsModel:
        """Compute the shortest paths through the `ShortestPath` algorithm.

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
            **kwargs: Extra arguments forwarded to `ShortestPath.run`.

        Returns:
            The computed paths grouped by mode.
        """
        assert modes is not None, "Modes must be provided"

        return ShortestPath(app=self.app).run(
            graph=graph,
            nodes=nodes,
            modes=modes.modes,
            timestamps=timestamps,
            node_mode_field=node_mode_field,
            link_mode_field=link_mode_fields,
            turn_mode_field=turn_mode_field,
            node_cost_field=node_cost_field,
            link_cost_field=link_cost_field,
            turn_cost_field=turn_cost_field,
            turn_prohibited_field=turn_prohibited_field,
            **kwargs,
        )


__all__ = ["Dispatcher", "DispatcherOperation"]
