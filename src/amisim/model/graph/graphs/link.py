from __future__ import annotations

from collections.abc import Callable, Hashable
from copy import deepcopy
from typing import Any


class Link(dict[Any, Any]):
    """Directed graph link from node ``i`` to node ``j``."""

    def __init__(self, idx: Hashable, i: Hashable, j: Hashable, **kwargs: Any) -> None:
        """Create a link with an identifier, start node, and end node."""
        super().__init__(**kwargs)
        self["idx"] = idx
        self["i"] = i
        self["j"] = j

    def combine(self, element: Link, n_intervals_of_self: int, n_intervals_of_element: int) -> None:
        for key, new_value in element.items():
            if key not in self:
                if isinstance(new_value, list):
                    first = new_value[0] if new_value else None  # type: ignore
                    self[key] = [first] * n_intervals_of_self
                    self[key].extend(new_value)
                elif isinstance(new_value, tuple):
                    first = new_value[0] if new_value else None  # type: ignore
                    self[key] = tuple([first] * n_intervals_of_self)
                    self[key] = self[key] + tuple(new_value)
                else:
                    self[key] = new_value
            else:
                old_value = self.get(key)
                if old_value is not None:
                    if isinstance(old_value, list):
                        if isinstance(new_value, (tuple, list)):
                            old_value.extend(list(new_value))
                        else:
                            old_value.extend([new_value] * n_intervals_of_element)
                    elif isinstance(old_value, tuple):
                        if isinstance(new_value, (tuple, list)):
                            old_value = old_value + tuple(new_value)
                        else:
                            old_value = old_value + tuple([new_value] * n_intervals_of_element)
                        self[key] = old_value
                    else:
                        self[key] = new_value

    @property
    def idx(self) -> Hashable:
        """Link identifier."""
        return self["idx"]

    @property
    def i(self) -> Hashable:
        """Start node identifier."""
        return self["i"]

    @property
    def j(self) -> Hashable:
        """End node identifier."""
        return self["j"]

    def copy(self) -> Link:
        """Return a deep copy of the link."""
        return deepcopy(self)

    def set_value(self, key: Any, value: Any) -> None:
        """Set a value for a given key in the link."""
        if key in ["idx", "i", "j"]:
            raise KeyError(f"Cannot modify reserved key '{key}' in Link.")
        elif key not in self:
            self[key] = value
        else:
            if isinstance(self[key], list):
                ele = self[key]
                for idx in range(len(ele)):
                    ele[idx] = value
            elif isinstance(self[key], tuple):
                ele = list(self[key])
                for idx in range(len(ele)):
                    ele[idx] = value
                self[key] = tuple(ele)
            else:
                self[key] = value

    def reset(self, name: str, value: Any | Callable[[Link, int | None], Any]) -> None:
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


__all__ = ["Link"]
