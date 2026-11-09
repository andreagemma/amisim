"""Exceptions raised by :mod:`graph`."""


class GraphError(Exception):
    """Base exception for the package."""


class ExistingNodeError(GraphError, KeyError):
    """An attempt was made to add a node that already exists in the graph."""


class ExistingLinkError(GraphError, KeyError):
    """An attempt was made to add a link that already exists in the graph."""


class ExistingTurnError(GraphError, KeyError):
    """An attempt was made to add a turn that already exists in the graph."""


class MissingLinkError(GraphError, KeyError):
    """An attempt was made to reference a link that does not exist in the graph."""


class MissingNodeError(GraphError, KeyError):
    """An attempt was made to reference a node that does not exist in the graph."""


__all__ = [
    "ExistingLinkError",
    "ExistingNodeError",
    "ExistingTurnError",
    "GraphError",
    "MissingLinkError",
    "MissingNodeError",
]
