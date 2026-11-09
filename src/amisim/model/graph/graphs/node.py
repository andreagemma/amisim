from __future__ import annotations

from collections.abc import Callable, Hashable
from copy import deepcopy
from typing import Any


class Node(dict[Any, Any]):
    """Graph node keyed by a stable identifier and arbitrary attributes."""

    def __init__(self, idx: Hashable, **kwargs: Any) -> None:
        """Create a node with an identifier and optional extra attributes."""
        super().__init__(**kwargs)
        self["idx"] = idx

    def combine(self, element: Node, n_intervals_of_self: int, n_intervals_of_element: int) -> None:
        for key, new_value in element.items():
            if key not in self:
                if isinstance(new_value, list):
                    first = new_value[0] if new_value else None  # type: ignore
                    self[key] = [first] * n_intervals_of_self
                    self[key].extend(new_value)
                elif isinstance(new_value, tuple):
                    first = new_value[0] if new_value else None  # type: ignore
                    self[key] = tuple([first] * n_intervals_of_self)  # type: ignore
                    self[key] = self[key] + tuple(new_value)  # type: ignore
                else:
                    self[key] = new_value
            else:
                old_value = self.get(key)
                if old_value is not None:
                    if isinstance(old_value, list):
                        if isinstance(new_value, (tuple, list)):
                            old_value.extend(list(new_value))  # type: ignore
                        else:
                            old_value.extend([new_value] * n_intervals_of_element)  # type: ignore
                    elif isinstance(old_value, tuple):
                        if isinstance(new_value, (tuple, list)):
                            old_value = old_value + tuple(new_value)  # type: ignore
                        else:
                            old_value = old_value + tuple([new_value] * n_intervals_of_element)  # type: ignore
                        self[key] = old_value
                    else:
                        self[key] = new_value

    @property
    def idx(self) -> Hashable:
        """Node identifier."""
        return self["idx"]

    def copy(self) -> Node:
        """Return a deep copy of the node."""
        return deepcopy(self)

    def reset(self, name: str, value: Any | Callable[[Node, int | None], Any]) -> None:
        if isinstance(self[name], (list, tuple)):
            n = len(self[name])
            if callable(value):
                self[name] = [value(self, i) for i in range(n)]
            elif isinstance(value, (list, tuple)):
                self[name] = value
            else:
                self[name] = [value for _ in range(n)]
        else:
            if callable(value):
                self[name] = value(self, None)
            else:
                self[name] = value


__all__ = ["Node"]
