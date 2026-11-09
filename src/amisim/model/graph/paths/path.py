"""Numba-accelerated path between two nodes at a departure time."""

from __future__ import annotations

import copyreg
from collections.abc import Iterable
from pathlib import Path as FilePath
from typing import Any

from serializer import dump, load


class Path:
    """A path between two nodes at a departure time, backed by numba typed storage."""
    
    def __init__(self, 
                 source: int, 
                 target:int, 
                 t_base: int, 
                 t_start: int, 
                 links: Iterable[int], 
                 costs: Iterable[float], 
                 mode: str, 
                 tot_cost: float | None = None, 
                 k: int = 1,
                 path_flow: float = 0.0
                 ):
        """Create a path and store its link sequence and cumulative costs."""
        self.source: int = source
        self.target: int = target
        self.t_start: int = t_start
        self.t_base: int = t_base
        self.t: int = t_base + t_start
        self.k: int = k
        self.mode: str | None = mode
        self.links: tuple[int, ...] = tuple(links)
        self.costs: tuple[float, ...] = tuple(costs)
        if tot_cost is None:
            tot_cost = costs[len(costs) - 1] if len(costs) > 0 else 0.0
        else:
            tot_cost = 0.0
        self.tot_cost: float = tot_cost
        self.path_flow: float = path_flow

    def key(self):
        """Return the lookup key used by path containers."""
        return Path.calc_key(source=self.source, target=self.target, t_start=self.t_start, mode=self.mode)

    @staticmethod
    def calc_key(source: int, target: int, t_start: int, mode: str | None) -> str:
        """Calculate the canonical key for the path."""
        return f"{source},{target},{t_start},{mode}"

    def copy(self):
        """Return a deep copy of the path."""
        return Path(
            source=self.source,
            target=self.target,
            t_start=self.t_start,
            links=self.links.copy(),
            costs=self.costs.copy(),
            mode=self.mode,
            tot_cost=self.tot_cost,
            t_base=self.t_base,
            k=self.k,
            path_flow=self.path_flow,
        )

    def has_link(self, id_link):
        """Return ``True`` when ``id_link`` appears in the path."""
        return id_link in self.links

    def counts_link(self, id_link):
        """Count how many times ``id_link`` appears in the path."""
        return self.links.count(id_link)

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the path."""
        return {
            "source": self.source,
            "target": self.target,
            "t_start": self.t_start,
            "t_base": self.t_base,
            "t": self.t,
            "k": self.k,
            "mode": self.mode,
            "links": self.links,
            "costs": self.costs,
            "tot_cost": self.tot_cost,
            "path_flow": self.path_flow,
        }


__all__ = ["Path"]
