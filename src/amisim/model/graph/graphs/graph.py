from __future__ import annotations

import random as rnd
import warnings
from collections.abc import Callable, Generator, Hashable, Iterable
from copy import deepcopy
from pathlib import Path as FilePath
from typing import Any

import numpy as np

from ..utils import time_index
from .action_policy import ActionPolicy
from .exceptions import (
    ExistingLinkError,
    ExistingNodeError,
    ExistingTurnError,
    MissingLinkError,
    MissingNodeError,
)
from .link import Link
from .node import Node
from .turn import Turn

Numeric = int | float


class Graph(dict[Any, Any]):
    """Graph structure used to manage nodes, directed links, and turns."""

    def __init__(
        self,
        t0: float | int = 0,
        total_time: float | int = 60,
        delta_t: float | int = 15,
        **kwargs: Any,
    ) -> None:
        """Create an empty graph with a time discretization.

        Args:
            t0: Start of the modelled time horizon.
            total_time: Duration of the modelled time horizon.
            delta_t: Duration of each time interval.
            **kwargs: Extra initial mapping values; graph indexes are initialized
                by the constructor.
        """
        super().__init__()
        self.update(**kwargs)
        self["links"] = {}
        self["links_ij"] = {}
        self["nodes"] = {}
        self["turns"] = {}
        self["turns_ij"] = {}
        self["modes"] = set()
        self["t0"] = t0
        self["total_time"] = total_time
        self["delta_t"] = delta_t
        self["num_intervals"] = int(total_time // delta_t)

    def get_sample_link(
        self,
        fn_filter: Callable[[Link], bool] | None = None,
        random: bool = False,
        random_state: int = 42,
    ) -> Link | None:
        """Return a matching link, selected deterministically or at random.

        Args:
            fn_filter: Optional predicate used to filter links.
            random: Whether to choose a random matching link.
            random_state: Seed used for a reproducible random choice.

        Returns:
            The selected link, or ``None`` if no link matches.
        """
        links = (
            list(self["links"].values())
            if fn_filter is None
            else [link for link in self["links"].values() if fn_filter(link)]
        )
        if not links:
            return None
        if random:
            return rnd.Random(random_state).choice(links)
        return links[0]

    def get_sample_node(
        self,
        fn_filter: Callable[[Node], bool] | None = None,
        random: bool = False,
        random_state: int = 42,
    ) -> Node | None:
        """Return a matching node, selected deterministically or at random.

        Args:
            fn_filter: Optional predicate used to filter nodes.
            random: Whether to choose a random matching node.
            random_state: Seed used for a reproducible random choice.

        Returns:
            The selected node, or ``None`` if no node matches.
        """
        nodes = (
            list(self["nodes"].values())
            if fn_filter is None
            else [node for node in self["nodes"].values() if fn_filter(node)]
        )
        if not nodes:
            return None
        if random:
            return rnd.Random(random_state).choice(nodes)
        return nodes[0]

    def get_sample_turn(
        self,
        fn_filter: Callable[[Turn], bool] | None = None,
        random: bool = False,
        random_state: int = 42,
    ) -> Turn | None:
        """Return a matching turn, selected deterministically or at random.

        Args:
            fn_filter: Optional predicate used to filter turns.
            random: Whether to choose a random matching turn.
            random_state: Seed used for a reproducible random choice.

        Returns:
            The selected turn, or ``None`` if no turn matches.
        """
        turns = (
            list(self["turns"].values())
            if fn_filter is None
            else [turn for turn in self["turns"].values() if fn_filter(turn)]
        )
        if not turns:
            return None
        if random:
            return rnd.Random(random_state).choice(turns)
        return turns[0]

    def shift_time(self, delta: float | int) -> None:
        """Shift the graph's time origin by ``delta``."""
        self["t0"] += delta

    def copy_from(self, other) -> Graph:
        if isinstance(other, dict):
            if "delta_t" in other:
                self["delta_t"] = other["delta_t"]
            if "t0" in other:
                self["t0"] = other["t0"]
            if "num_intervals" in other:
                self["num_intervals"] = other["num_intervals"]
            if "modes" in other:
                self["modes"] = other["modes"]
        else:
            if hasattr(other, "delta_t"):
                self["delta_t"] = other.delta_t
            if hasattr(other, "t0"):
                self["t0"] = other.t0
            if hasattr(other, "num_intervals"):
                self["num_intervals"] = other.num_intervals
            if hasattr(other, "modes"):
                self["modes"] = other.modes
        self["nodes"] = {}
        self["links"] = {}
        self["links_ij"] = {}
        self["turns"] = {}
        self["turns_ij"] = {}
        if hasattr(other, "get_all_nodes"):
            for node in other.get_all_nodes():
                self.add_node(**node, on_existing=ActionPolicy.SKIP)
        if hasattr(other, "get_all_links"):
            for link in other.get_all_links():
                self.add_link(**link, on_existing=ActionPolicy.SKIP, on_missing_node=ActionPolicy.SKIP)
        if hasattr(other, "get_all_turns"):
            for turn in other.get_all_turns():
                self.add_turn(**turn, on_existing=ActionPolicy.SKIP, on_missing_link=ActionPolicy.SKIP)
        return self

    def merge(self, other: Graph | None, copy: bool = False, inplace: bool = True) -> Graph:
        """Append another graph's time horizon and entities to this graph.

        Args:
            other: Graph to append, or ``None`` to leave this graph unchanged.
            copy: Whether to copy ``other`` before adjusting or merging it.
            inplace: Whether to update this graph; otherwise merge into a copy.

        Returns:
            The updated graph, or its copy when ``inplace`` is false.
        """
        if not inplace:
            self = self.copy()
        if other is None:
            return self
        if copy:
            other = other.copy()

        if not isinstance(other, Graph):  # type: ignore
            raise ValueError("The object to merge must be an instance of Graph.")

        if self.delta_t != other.delta_t:
            raise ValueError("Cannot merge graphs with different delta_t values.")

        while other.tend < self.tend:
            # print(f"Shifting other graph by 1440 minutes because other graph starts at {other.t0} and current graph ends at {self.tend}.")
            other.shift_time(1440)

        if not (other.tstart == 0 and self.tend == 1440):
            other_successive = self.tstart <= other.tstart < self.tend and other.tend > self.tend
            if not (self.tend == other.tstart or other_successive):
                raise ValueError("Graphs do not overlap in time and cannot be merged.")
            if other_successive:
                other.cut_time_slice(time_start=self.tend, time_end=other.tend)
        for new_node in other["nodes"].values():
            if new_node.idx not in self["nodes"]:
                self.add_node(**new_node)
            else:
                n_self = self["nodes"][new_node.idx]
                n_self.combine(new_node, self.num_intervals, other.num_intervals)
        for new_link in other["links"].values():
            if new_link.idx not in self["links"]:
                self.add_link(**new_link, on_existing=ActionPolicy.RAISE, on_missing_node=ActionPolicy.WARN)
            else:
                l_self = self["links"][new_link.idx]
                l_self.combine(new_link, self.num_intervals, other.num_intervals)
        for new_turn in other["turns"].values():
            if new_turn.idx not in self["turns"]:
                self.add_turn(
                    **new_turn,
                    on_existing=ActionPolicy.RAISE,
                    on_missing_link=ActionPolicy.WARN,
                )
            else:
                t_self = self["turns"][new_turn.idx]
                old_pair = (t_self.in_link, t_self.out_link)
                t_self.combine(new_turn, self.num_intervals, other.num_intervals)
                new_pair = (t_self.in_link, t_self.out_link)
                if new_pair != old_pair:
                    self._unindex_turn(t_self, old_pair)
                    self._get_turn_index()[new_pair] = t_self
        self["total_time"] = self["total_time"] + other["total_time"]
        self["num_intervals"] = int(self["total_time"] // self["delta_t"])
        return self

    @property
    def delta_t(self) -> float | int:
        """Duration of each time interval."""
        return self["delta_t"]

    @property
    def t0(self) -> float | int:
        """Base time used by time-dependent attributes."""
        return self["t0"]

    @t0.setter
    def t0(self, value: float | int) -> None:
        """Set the time origin."""
        self["t0"] = value

    @property
    def tend(self) -> float | int:
        """End time of the modelled time horizon."""
        return self["t0"] + self["total_time"]

    @property
    def tstart(self) -> float | int:
        """Start time of the modelled time horizon."""
        return self["t0"]

    @tstart.setter
    def tstart(self, value: float | int) -> None:
        """Set the start of the graph's time horizon."""
        self["t0"] = value

    @property
    def total_time(self) -> float | int:
        """Total modelled time horizon."""
        return self["total_time"]

    @property
    def num_intervals(self) -> int:
        """Number of time intervals in the graph horizon."""
        return self["num_intervals"]

    def save(self, filename: str | FilePath) -> None:
        """Serialize the graph to ``filename`` using dill."""
        try:
            import dill  # pyright: ignore[reportMissingTypeStubs]

            with open(filename, "wb") as file:
                dill.dump(self, file, dill.HIGHEST_PROTOCOL)  # pyright: ignore[reportUnknownMemberType]
        except ImportError as e:
            raise ImportError("dill is required for saving the graph.") from e

    @staticmethod
    def load(filename: str | FilePath) -> Graph:
        """Load a serialized graph from ``filename``."""
        try:
            import dill  # pyright: ignore[reportMissingTypeStubs]

            with open(filename, "rb") as file:
                return dill.load(file)  # pyright: ignore[reportUnknownMemberType]
        except ImportError as e:
            raise ImportError("dill is required for loading the graph.") from e

    def copy(self) -> Graph:
        """Return a deep copy of the graph."""
        return deepcopy(self)

    def add_link(
        self,
        idx: Hashable,
        i: Hashable,
        j: Hashable,
        on_existing: ActionPolicy = ActionPolicy.RAISE,
        on_missing_node: ActionPolicy = ActionPolicy.RAISE,
        **kwargs: Any,
    ) -> Link | None:
        """Add a directed link to the graph.

        Args:
            idx: Unique link identifier.
            i: Start node identifier.
            j: End node identifier.
            on_existing: Policy for an already-used link identifier.
            on_missing_node: Policy for missing endpoint nodes.
            **kwargs: Additional link attributes.

        Returns:
            The added link, or ``None`` when the policy skips the operation.
        """
        kwargs["delta_t"] = self.delta_t
        kwargs["total_time"] = self.total_time

        if not self._handle_missing_node(i, "Start", on_missing_node):
            return None
        if not self._handle_missing_node(j, "End", on_missing_node):
            return None

        links = self["links"]
        if idx in links:
            if on_existing == ActionPolicy.RAISE:
                raise ExistingLinkError(f"Link with id {idx} already exists.")
            if on_existing == ActionPolicy.WARN:
                warnings.warn(f"Link with id {idx} already exists.", stacklevel=2)
            if on_existing in {ActionPolicy.IGNORE, ActionPolicy.SKIP}:
                return links[idx]

            old_link = links[idx]
            self["links_ij"].pop((old_link.i, old_link.j), None)

        link = Link(idx=idx, i=i, j=j, **kwargs)
        links[idx] = link
        self["links_ij"][(i, j)] = link
        return link

    def _handle_missing_node(
        self,
        idx: Hashable,
        role: str,
        policy: ActionPolicy,
    ) -> bool:
        """Internal helper: handle missing node."""
        nodes = self["nodes"]
        if idx in nodes:
            return True
        if policy == ActionPolicy.RAISE:
            raise MissingNodeError(f"{role} node with id {idx} does not exist.")
        if policy == ActionPolicy.WARN:
            warnings.warn(f"{role} node with id {idx} does not exist. Skipping.", stacklevel=3)
        elif policy == ActionPolicy.SKIP:
            return False
        elif policy == ActionPolicy.REPLACE:
            self.add_node(idx, on_existing=ActionPolicy.SKIP)
        return True

    def add_node(
        self,
        idx: Hashable,
        on_existing: ActionPolicy = ActionPolicy.RAISE,
        **kwargs: Any,
    ) -> Node:
        """Add a node to the graph.

        Args:
            idx: Unique node identifier.
            on_existing: Policy for an already-used node identifier.
            **kwargs: Additional node attributes.

        Returns:
            The added node, or the existing node for ignore/skip policies.
        """
        nodes = self["nodes"]
        if idx in nodes:
            if on_existing == ActionPolicy.RAISE:
                raise ExistingNodeError(f"Node with id {idx} already exists.")
            if on_existing == ActionPolicy.WARN:
                warnings.warn(f"Node with id {idx} already exists.", stacklevel=2)
            if on_existing in {ActionPolicy.IGNORE, ActionPolicy.SKIP}:
                return nodes[idx]

        node = Node(idx=idx, **kwargs)
        nodes[idx] = node
        return node

    def add_turn(
        self,
        idx: Hashable,
        in_link: Hashable,
        out_link: Hashable,
        on_existing: ActionPolicy = ActionPolicy.RAISE,
        on_missing_link: ActionPolicy = ActionPolicy.RAISE,
        **kwargs: Any,
    ) -> Turn | None:
        """Add a turn between two directed links.

        Args:
            idx: Unique turn identifier.
            in_link: Incoming link identifier.
            out_link: Outgoing link identifier.
            on_existing: Policy for an already-used turn identifier.
            on_missing_link: Policy for missing incoming or outgoing links.
            **kwargs: Additional turn attributes.

        Returns:
            The added turn, or ``None`` when the policy skips the operation.
        """
        kwargs["delta_t"] = self.delta_t
        kwargs["total_time"] = self.total_time

        if not self._handle_missing_link(in_link, "Incoming", on_missing_link):
            return None
        if not self._handle_missing_link(out_link, "Outgoing", on_missing_link):
            return None

        turns = self["turns"]
        if idx in turns:
            if on_existing == ActionPolicy.RAISE:
                raise ExistingTurnError(f"Turn with id {idx} already exists.")
            if on_existing == ActionPolicy.WARN:
                warnings.warn(f"Turn with id {idx} already exists.", stacklevel=2)
            if on_existing in {ActionPolicy.IGNORE, ActionPolicy.SKIP}:
                return turns[idx]
            self._unindex_turn(turns[idx])

        turn = Turn(idx=idx, in_link=in_link, out_link=out_link, **kwargs)
        turns[idx] = turn
        turn_ij = (in_link, out_link)
        self._get_turn_index()[turn_ij] = turn
        return turn

    def _handle_missing_link(
        self,
        idx: Hashable,
        role: str,
        policy: ActionPolicy,
    ) -> bool:
        """Internal helper: handle missing link."""
        links = self["links"]
        if idx in links:
            return True
        if policy == ActionPolicy.RAISE:
            raise MissingLinkError(f"{role} link with id {idx} does not exist.")
        if policy == ActionPolicy.WARN:
            warnings.warn(f"{role} link with id {idx} does not exist.", stacklevel=3)
        elif policy == ActionPolicy.SKIP:
            return False
        return True

    def _get_turn_index(self) -> dict[tuple[Hashable, Hashable], Turn]:
        """Return the turn lookup index, rebuilding it for older serialized graphs."""
        if "turns_ij" not in self:
            self["turns_ij"] = {(turn.in_link, turn.out_link): turn for turn in self.get_all_turns()}
        return self["turns_ij"]

    def _unindex_turn(
        self,
        turn: Turn,
        pair: tuple[Hashable, Hashable] | None = None,
    ) -> None:
        """Remove a turn from the pair index and restore any duplicate pair."""
        pair = pair if pair is not None else (turn.in_link, turn.out_link)
        index = self._get_turn_index()
        if index.get(pair) is not turn:
            return
        index.pop(pair, None)
        for remaining in self.get_all_turns():
            if remaining is not turn and (remaining.in_link, remaining.out_link) == pair:
                index[pair] = remaining

    def get_all_links_idx(self) -> list[Hashable]:
        """Return link identifiers in insertion order.

        Returns:
            The list of link identifiers.
        """
        return list(self["links"].keys())

    def get_all_links(self) -> Generator[Link]:
        """Yield all links in insertion order.

        Yields:
            Each link in the graph.
        """
        yield from self["links"].values()

    def get_link_by_nodes(self, i: Hashable, j: Hashable) -> Link | None:
        """Return the link between two nodes, if present.

        Args:
            i: Start node identifier.
            j: End node identifier.

        Returns:
            The matching directed link, or ``None`` if it does not exist.
        """
        return self["links_ij"].get((i, j), None)

    def has_link_by_nodes(self, i: Hashable, j: Hashable) -> bool:
        """Check whether a directed link exists between two nodes.

        Args:
            i: Start node identifier.
            j: End node identifier.

        Returns:
            ``True`` if the link exists.
        """
        return (i, j) in self["links_ij"]

    def get_all_nodes(self) -> Generator[Node]:
        """Yield all nodes in insertion order.

        Yields:
            Each node in the graph.
        """
        yield from self["nodes"].values()

    def get_all_turns(self) -> Generator[Turn]:
        """Yield all turns in insertion order.

        Yields:
            Each turn in the graph.
        """
        yield from self["turns"].values()

    def apply_links(self, fn: Callable[[Link], Any] | None = None) -> None:
        """Apply a callback to every link.

        Args:
            fn: Callback receiving each link. Must not be ``None``.
        """
        if fn is None:
            msg = "fn must be callable"
            raise TypeError(msg)
        for link in self.get_all_links():
            fn(link)

    def apply_nodes(self, fn: Callable[[Node], Any] | None = None) -> None:
        """Apply a callback to every node.

        Args:
            fn: Callback receiving each node. Must not be ``None``.
        """
        if fn is None:
            msg = "fn must be callable"
            raise TypeError(msg)
        for node in self.get_all_nodes():
            fn(node)

    def apply_turns(self, fn: Callable[[Turn], Any] | None = None) -> None:
        """Apply a callback to every turn.

        Args:
            fn: Callback receiving each turn. Must not be ``None``.
        """
        if fn is None:
            msg = "fn must be callable"
            raise TypeError(msg)
        for turn in self.get_all_turns():
            fn(turn)

    def resize_attributes(
        self,
        new_total_time: Numeric | None = None,
        new_delta_t: Numeric | None = None,
    ) -> None:
        """Resize the graph horizon and its time-dependent attributes.

        Args:
            new_total_time: Optional replacement horizon duration.
            new_delta_t: Optional replacement interval duration.
        """
        old_total_time = self["total_time"]
        old_delta_t = self["delta_t"]
        total_time = old_total_time if new_total_time is None else new_total_time
        delta_t = old_delta_t if new_delta_t is None else new_delta_t

        new_length = int(total_time // delta_t)

        if total_time == old_total_time and delta_t == old_delta_t:
            return
        elif total_time != old_total_time and delta_t == old_delta_t:
            for element in (*self.get_all_links(), *self.get_all_nodes(), *self.get_all_turns()):
                for key in element:
                    value = element[key]
                    if isinstance(value, (tuple, list, np.ndarray)):
                        original_length = int(len(value))  # type: ignore
                        if original_length == 0:
                            continue

                        if isinstance(value, tuple):
                            new_tvalue = list(value)  # type: ignore
                            if total_time > old_total_time:
                                new_tvalue.extend([new_tvalue[-1]] * (new_length - original_length))  # type: ignore
                            elif total_time < old_total_time:
                                new_tvalue = new_tvalue[:new_length]  # type: ignore
                            element[key] = tuple(new_tvalue)  # type: ignore
                        elif isinstance(value, list):
                            new_lvalue = list(value)  # type: ignore
                            if total_time > old_total_time:
                                new_lvalue.extend([new_lvalue[-1]] * (new_length - original_length))  # type: ignore
                            elif total_time < old_total_time:
                                new_lvalue = new_lvalue[:new_length]  # type: ignore
                            element[key] = new_lvalue
                        else:
                            new_array: np.ndarray = np.array(value)  # type: ignore
                            if total_time > old_total_time:
                                new_array = np.concatenate(
                                    [
                                        new_array,
                                        np.full((new_length - original_length,), new_array[-1]),
                                    ]
                                )
                            elif total_time < old_total_time:
                                new_array = new_array[:new_length]
                            element[key] = new_array
        else:
            for element in (*self.get_all_links(), *self.get_all_nodes(), *self.get_all_turns()):
                for key in element:
                    value = element[key]
                    if isinstance(value, (tuple, list, np.ndarray)):
                        old_length = len(value)  # type: ignore
                        if old_length != new_length:
                            if old_length == 0 or new_length == 0:
                                if isinstance(value, tuple):
                                    element[key] = tuple()
                                elif isinstance(value, list):
                                    element[key] = []
                                else:
                                    element[key] = np.array([])
                                continue

                            if isinstance(value, tuple):
                                element[key] = tuple(
                                    np.interp(
                                        np.linspace(0, 1, new_length),
                                        np.linspace(0, 1, old_length),
                                        value,  # type: ignore
                                    )
                                )
                            elif isinstance(value, list):
                                element[key] = list(
                                    np.interp(
                                        np.linspace(0, 1, new_length),
                                        np.linspace(0, 1, old_length),
                                        value,  # type: ignore
                                    )
                                )
                            else:  # np.ndarray
                                element[key] = np.interp(
                                    np.linspace(0, 1, new_length),
                                    np.linspace(0, 1, old_length),
                                    value,  # type: ignore
                                )

        self["total_time"] = total_time
        self["delta_t"] = delta_t
        self["num_intervals"] = new_length

        for element in (*self.get_all_links(), *self.get_all_turns()):
            element["total_time"] = total_time
            element["delta_t"] = delta_t

    def get_intervals(self) -> list[int]:
        """Return interval start times based on the current horizon.

        Returns:
            The start time of each simulation interval, rounded to integers.
        """
        return (np.arange(int(self["num_intervals"])) * self["delta_t"] + self["t0"]).round().astype(int).tolist()

    def create_array_attribute(
        self,
        value: Any,
        value_total_time: float | int | None = None,
        value_delta_t: float | int | None = None,
    ) -> list[Any]:
        """Create or resize a time-series attribute to match a target horizon.

        Args:
            value: Scalar or sequence to normalize.
            value_total_time: Target duration; defaults to the graph duration.
            value_delta_t: Target interval duration; defaults to the graph interval.

        Returns:
            A list with one value per target interval.
        """
        if not isinstance(value, (tuple, list, np.ndarray)):
            value = [value]

        if value_total_time is None:
            value_total_time = self["total_time"]
        if value_delta_t is None:
            value_delta_t = self["delta_t"]

        new_length = int(value_total_time // value_delta_t)  # type: ignore
        old_length = len(value)  # type: ignore

        if old_length == 0:
            return []

        if old_length != new_length:
            value = list(
                np.interp(
                    np.linspace(0, 1, new_length),
                    np.linspace(0, 1, old_length),
                    value,  # type: ignore
                ).tolist()
            )
        return list(value)  # type: ignore

    def get_link(self, idx: Hashable) -> Link | None:
        """Return a link by identifier, or ``None`` when missing.

        Args:
            idx: Link identifier.

        Returns:
            The matching link, or ``None``.
        """
        return self["links"].get(idx)

    def get_link_or_error(self, idx: Hashable) -> Link:
        """Return a link by identifier.

        Args:
            idx: Link identifier.

        Returns:
            The matching link.

        Raises:
            KeyError: If no link has the identifier.
        """
        return self["links"][idx]

    def get_node(self, idx: Hashable) -> Node | None:
        """Return a node by identifier, or ``None`` when missing.

        Args:
            idx: Node identifier.

        Returns:
            The matching node, or ``None``.
        """
        return self["nodes"].get(idx)

    def get_node_or_error(self, idx: Hashable) -> Node:
        """Return a node by identifier.

        Args:
            idx: Node identifier.

        Returns:
            The matching node.

        Raises:
            KeyError: If no node has the identifier.
        """
        return self["nodes"][idx]

    def get_turn(self, idx: Hashable) -> Turn | None:
        """Return a turn by identifier, or ``None`` when missing.

        Args:
            idx: Turn identifier.

        Returns:
            The matching turn, or ``None``.
        """
        return self["turns"].get(idx)

    def get_turn_or_error(self, idx: Hashable) -> Turn:
        """Return a turn by identifier.

        Args:
            idx: Turn identifier.

        Returns:
            The matching turn.

        Raises:
            KeyError: If no turn has the identifier.
        """
        return self["turns"][idx]

    def get_turn_by_links(self, in_link: Hashable, out_link: Hashable) -> Turn | None:
        """Return a turn by its incoming and outgoing link identifiers.

        Args:
            in_link: Incoming link identifier.
            out_link: Outgoing link identifier.

        Returns:
            The matching turn, or ``None`` if it does not exist.
        """
        return self._get_turn_index().get((in_link, out_link))

    def get_turn_by_links_or_error(self, in_link: Hashable, out_link: Hashable) -> Turn:
        """Return a turn by its incoming and outgoing link identifiers.

        Args:
            in_link: Incoming link identifier.
            out_link: Outgoing link identifier.

        Returns:
            The matching turn.

        Raises:
            KeyError: If the turn does not exist.
        """
        return self._get_turn_index()[(in_link, out_link)]

    def remove_link(self, idx: Hashable, cascade: bool = False) -> None:
        """Remove a link by identifier.

        Args:
            idx: Link identifier.
            cascade: Whether to also remove turns that reference the link.
        """
        if cascade:
            turns_to_remove = [turn.idx for turn in self.get_all_turns() if turn.in_link == idx or turn.out_link == idx]
            self.remove_turns(turns_to_remove)
        link = self["links"].pop(idx, None)
        if link is not None:
            self["links_ij"].pop((link.i, link.j), None)

    def remove_links(self, idx: Iterable[Hashable], cascade: bool = False) -> None:
        """Remove multiple links by identifier.

        Args:
            idx: Link identifiers to remove.
            cascade: Whether to also remove turns that reference these links.
        """
        link_ids = set(idx)
        if cascade:
            turns_to_remove = [
                turn.idx for turn in self.get_all_turns() if turn.in_link in link_ids or turn.out_link in link_ids
            ]
            self.remove_turns(turns_to_remove)
        for link_idx in link_ids:
            link = self["links"].pop(link_idx, None)
            if link is not None:
                self["links_ij"].pop((link.i, link.j), None)

    def remove_node(self, idx: Hashable, cascade: bool = False) -> None:
        """Remove a node by identifier.

        Args:
            idx: Node identifier.
            cascade: Whether to remove dependent links and turns.
        """
        if cascade:
            links_to_remove = [link.idx for link in self.get_all_links() if link.i == idx or link.j == idx]
            self.remove_links(links_to_remove, cascade=True)
        self["nodes"].pop(idx, None)

    def remove_nodes(self, idx: Iterable[Hashable], cascade: bool = False) -> None:
        """Remove multiple nodes by identifier.

        Args:
            idx: Node identifiers to remove.
            cascade: Whether to remove dependent links and turns.
        """
        node_ids = set(idx)
        if cascade:
            links_to_remove = [link.idx for link in self.get_all_links() if link.i in node_ids or link.j in node_ids]
            self.remove_links(links_to_remove, cascade=True)

        for node_idx in node_ids:
            self["nodes"].pop(node_idx, None)

    def remove_turn(self, idx: Hashable) -> None:
        """Remove a turn by identifier.

        Args:
            idx: Turn identifier.
        """
        turn = self["turns"].pop(idx, None)
        if turn is not None:
            self._unindex_turn(turn)

    def remove_turns(self, idx: Iterable[Hashable]) -> None:
        """Remove multiple turns by identifier.

        Args:
            idx: Turn identifiers to remove.
        """
        for turn_idx in set(idx):
            turn = self["turns"].pop(turn_idx, None)
            if turn is not None:
                self._unindex_turn(turn)

    def get_node_neighbors(
        self,
        idx: Hashable,
        include_in_links: bool = True,
        include_out_links: bool = True,
    ) -> list[Link]:
        """Return links connected to a node.

        Args:
            idx: Node identifier.
            include_in_links: Include links ending at the node.
            include_out_links: Include links starting at the node.

        Returns:
            The matching links in insertion order.
        """
        return [
            link
            for link in self.get_all_links()
            if (include_in_links and link.j == idx) or (include_out_links and link.i == idx)
        ]

    def get_nodes_neighbors(
        self,
        include_in_links: bool = True,
        include_out_links: bool = True,
    ) -> dict[Hashable, list[Link]]:
        """Return connected links for every node.

        Args:
            include_in_links: Include links ending at each node.
            include_out_links: Include links starting at each node.

        Returns:
            A mapping from node identifiers to their matching links.
        """
        return {
            node.idx: self.get_node_neighbors(
                node.idx,
                include_in_links=include_in_links,
                include_out_links=include_out_links,
            )
            for node in self.get_all_nodes()
        }

    def get_node_degree(
        self,
        idx: Hashable,
        include_in_links: bool = True,
        include_out_links: bool = True,
    ) -> int:
        """Return the number of links connected to a node.

        Args:
            idx: Node identifier.
            include_in_links: Count links ending at the node.
            include_out_links: Count links starting at the node.

        Returns:
            The number of matching links.
        """
        return len(
            self.get_node_neighbors(
                idx,
                include_in_links=include_in_links,
                include_out_links=include_out_links,
            )
        )

    def remove_isolated_nodes(self) -> None:
        """Remove nodes with no incoming or outgoing links."""
        neighbors = self.get_nodes_neighbors(include_in_links=True, include_out_links=True)
        isolated_nodes = [node.idx for node in self.get_all_nodes() if len(neighbors[node.idx]) == 0]
        self.remove_nodes(isolated_nodes, cascade=False)

    def remove_links_without_nodes(self, cascade: bool = False) -> None:
        """Remove links whose start or end node is missing.

        Args:
            cascade: Whether to also remove turns that reference those links.
        """
        all_node_ids = {node.idx for node in self.get_all_nodes()}
        links_to_remove = [
            link.idx for link in self.get_all_links() if link.i not in all_node_ids or link.j not in all_node_ids
        ]
        self.remove_links(links_to_remove, cascade=cascade)

    def remove_turns_without_links(self) -> None:
        """Remove turns whose incoming or outgoing link is missing."""
        all_link_ids = {link.idx for link in self.get_all_links()}
        turns_to_remove = [
            turn.idx
            for turn in self.get_all_turns()
            if turn.in_link not in all_link_ids or turn.out_link not in all_link_ids
        ]
        self.remove_turns(turns_to_remove)

    def remove_redundants(self) -> None:
        """Remove links without nodes, isolated nodes, and turns without links."""
        self.remove_links_without_nodes()
        self.remove_isolated_nodes()
        self.remove_turns_without_links()

    def nodes_by_filter(self, filter_func: Callable[[Node], bool]) -> Generator[Node, None, None]:
        """Yield nodes that satisfy a predicate.

        Args:
            filter_func: Predicate receiving a node.

        Yields:
            Each node for which the predicate returns ``True``.
        """
        for node in self.get_all_nodes():
            if filter_func(node):
                yield node

    def remove_nodes_by_filter(
        self,
        filter_func: Callable[[Node], bool],
        cascade: bool = False,
    ) -> None:
        """Remove nodes that satisfy a predicate.

        Args:
            filter_func: Predicate receiving a node.
            cascade: Whether to remove dependent links and turns.
        """
        self.remove_nodes((node.idx for node in self.nodes_by_filter(filter_func)), cascade=cascade)

    def links_by_filter(self, filter_func: Callable[[Link], bool]) -> Generator[Link, None, None]:
        """Yield links that satisfy a predicate.

        Args:
            filter_func: Predicate receiving a link.

        Yields:
            Each link for which the predicate returns ``True``.
        """
        for link in self.get_all_links():
            if filter_func(link):
                yield link

    def remove_links_by_filter(
        self,
        filter_func: Callable[[Link], bool],
        cascade: bool = False,
    ) -> None:
        """Remove links that satisfy a predicate.

        Args:
            filter_func: Predicate receiving a link.
            cascade: Whether to remove turns that reference those links.
        """
        self.remove_links((link.idx for link in self.links_by_filter(filter_func)), cascade=cascade)

    def turns_by_filter(self, filter_func: Callable[[Turn], bool]) -> Generator[Turn, None, None]:
        """Yield turns that satisfy a predicate.

        Args:
            filter_func: Predicate receiving a turn.

        Yields:
            Each turn for which the predicate returns ``True``.
        """
        for turn in self.get_all_turns():
            if filter_func(turn):
                yield turn

    def remove_turns_by_filter(
        self,
        filter_func: Callable[[Turn], bool],
        cascade: bool = False,
    ) -> None:
        """Remove turns that satisfy ``filter_func``.

        The ``cascade`` parameter is accepted for API symmetry and currently has
        no effect because turns have no dependent entities.

        Args:
            filter_func: Predicate receiving a turn.
            cascade: Accepted for symmetry; has no effect.
        """
        del cascade
        self.remove_turns(turn.idx for turn in self.turns_by_filter(filter_func))

    def time_index(self, time_value: float) -> int:
        """Return the interval index containing a time value.

        Args:
            time_value: Absolute time in the graph's horizon.

        Returns:
            The corresponding interval index, clamped to the available range.
        """
        return time_index(
            t0=self["t0"],
            delta_t=self["delta_t"],
            n_intervals=self["num_intervals"],
            time_value=time_value,
        )

    def cut_time_slice(
        self,
        time_start: float | int | None = None,
        time_end: float | int | None = None,
        rebase: float | int | None = None,
        inplace: bool = True,
    ) -> Graph:
        """Return a graph containing a slice of this graph's time horizon.

        Time-series attributes are sliced to the selected interval range.

        Args:
            time_start: Inclusive start time; defaults to the graph start.
            time_end: Exclusive end time, except that the graph horizon end
                includes its final interval; defaults to the graph end.
            rebase: Optional new start time for the returned slice.
            inplace: Whether to modify this graph instead of a deep copy.

        Returns:
            The sliced graph.
        """
        other = self if inplace else self.copy()

        time_end = time_end if time_end is not None else other.tend
        time_start = time_start if time_start is not None else other.tstart

        t_index_start = other.time_index(time_start)
        t_index_end = other.time_index(time_end)
        if time_end == other.tend:
            t_index_end += 1

        n_intervals = other.num_intervals
        for link in other.get_all_links():
            for name in link:
                if isinstance(link[name], (list, tuple)) and len(link[name]) == n_intervals:
                    link[name] = link[name][t_index_start:t_index_end]
        for turn in other.get_all_turns():
            for name in turn:
                if isinstance(turn[name], (list, tuple)) and len(turn[name]) == n_intervals:
                    turn[name] = turn[name][t_index_start:t_index_end]
        for node in other.get_all_nodes():
            for name in node:
                if isinstance(node[name], (list, tuple)) and len(node[name]) == n_intervals:
                    node[name] = node[name][t_index_start:t_index_end]

        other["t0"] = time_start
        other["total_time"] = time_end - time_start
        other["num_intervals"] = int(other.total_time // other.delta_t)
        if rebase is not None:
            other.t0 = rebase
        return other

    def reset_links(self, name: str, value: Any | Callable[[Link, int | None], Any]) -> None:
        """Set a link attribute to a value or compute it for each link.

        Callable values receive the link and either an interval index or
        ``None`` for scalar attributes.

        Args:
            name: Link attribute to reset.
            value: Replacement value or callback.
        """
        for link in self.get_all_links():
            if isinstance(link[name], (list, tuple)):
                if callable(value):  # type: ignore
                    link[name] = [value(link, i) for i in range(len(link[name]))]
                elif isinstance(value, (list, tuple)):
                    link[name] = value
                else:
                    link[name] = self.create_array_attribute(value)
            else:
                if callable(value):  # type: ignore
                    link[name] = value(link, None)
                else:
                    link[name] = value

    def reset_turns(self, name: str, value: Any | Callable[[Turn, int | None], Any]) -> None:
        """Set a turn attribute to a value or compute it for each turn.

        Callable values receive the turn and either an interval index or
        ``None`` for scalar attributes.

        Args:
            name: Turn attribute to reset.
            value: Replacement value or callback.
        """
        for turn in self.get_all_turns():
            if isinstance(turn[name], (list, tuple)):
                if callable(value):  # type: ignore
                    turn[name] = [value(turn, i) for i in range(len(turn[name]))]
                elif isinstance(value, (list, tuple)):
                    turn[name] = value
                else:
                    turn[name] = self.create_array_attribute(value)
            else:
                if callable(value):  # type: ignore
                    turn[name] = value(turn, None)
                else:
                    turn[name] = value

    def reset_nodes(self, name: str, value: Any | Callable[[Node, int | None], Any]) -> None:
        """Set a node attribute to a value or compute it for each node.

        Callable values receive the node and either an interval index or
        ``None`` for scalar attributes.

        Args:
            name: Node attribute to reset.
            value: Replacement value or callback.
        """
        for node in self.get_all_nodes():
            if isinstance(node[name], (list, tuple)):
                if callable(value):  # type: ignore
                    node[name] = [value(node, i) for i in range(len(node[name]))]
                elif isinstance(value, (list, tuple)):
                    node[name] = value
                else:
                    node[name] = self.create_array_attribute(value)
            else:
                if callable(value):  # type: ignore
                    node[name] = value(node, None)
                else:
                    node[name] = value

    def n_nodes(self) -> int:
        """Return the number of nodes."""
        return len(self.get("nodes", [])) or 0

    def n_links(self) -> int:
        """Return the number of directed links."""
        return len(self.get("links", [])) or 0

    def n_turns(self) -> int:
        """Return the number of turns."""
        return len(self.get("turns", [])) or 0

    @property
    def empty(self) -> bool:
        """Whether the graph contains no nodes, links, or turns."""
        return self.n_nodes() == 0 and self.n_links() == 0 and self.n_turns() == 0

    def to_str(self) -> str:
        """Return a concise summary of the graph and its time horizon.

        Returns:
            A formatted string with time metadata and entity counts.
        """
        n_nodes = len(self.get("nodes", [])) or 0
        n_links = len(self.get("links", [])) or 0
        n_turns = len(self.get("turns", [])) or 0
        delta_t = self.get("delta_t", 0) or 0
        t0 = self.get("t0", 0) or 0
        total_time = self.get("total_time", 0) or 0
        return f"Graph(t0={t0}, total_time={total_time}, delta_t={delta_t}, nodes={n_nodes}, links={n_links}, turns={n_turns})"


__all__ = ["Graph", "time_index"]
