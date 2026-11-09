from __future__ import annotations

from collections.abc import Generator, Hashable
from typing import Any

import pandas as pd

from .path import Path
from .path_container import PathContainer

Numeric = int | float

_PATH_FIELDS = ("source", "target", "t_start", "links", "costs", "tot_cost", "mode", "t_base", "path_flow")


class KPathContainer(PathContainer):
    """Abstract base class for collections with multiple paths per key."""

    def __init__(self, **kwargs: Any) -> None:
        """Create an empty k-path container."""
        super().__init__(**kwargs)

    def add_path(self, to_add: Path, k: int | None = None, **kwargs: dict[str, Any]) -> None:
        """Add one path at an optional k position."""
        raise NotImplementedError

    def get_path(
        self,
        source: Hashable,
        target: Hashable,
        t_start: Numeric,
        mode: str | None = None,
        k: int = 0,
        **kwargs: Any,
    ) -> Path | None:
        """Return a single path by k position."""
        for p in self.filter(source=source, target=target, t_start=t_start, mode=mode, **kwargs):
            if p.k == k:
                return p
        return None

    def all_kpaths(
        self,
        **kwargs: Any,
    ) -> Generator[tuple[tuple[Hashable, Hashable, Numeric, str | None], list[Path]], None, None]:
        """Yield each canonical key with its path list."""
        raise NotImplementedError

    def max_k(self, **kwargs: Any) -> int:
        """Return the largest stored k index, or ``-1`` when empty."""
        return max((max(int(path.k), 0) for path in self.all_paths(**kwargs)), default=-1)

    @classmethod
    def from_pandas(
        cls, df: pd.DataFrame | dict[str, Any] | list[dict[str, Any]], **kwargs: dict[str, Any]
    ) -> KPathContainer:
        ret = cls()
        _df: pd.DataFrame = df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)

        grps = _df.groupby(["source", "target", "t_start", "mode"])
        for _, index in grps.groups.items():
            group: pd.DataFrame = _df.loc[index, :].sort_values(by="tot_cost")
            for k, (_, row) in enumerate(group.iterrows()):
                args = {str(key): value for key, value in dict(row.to_dict()).items()}
                path = Path(**{key: args[key] for key in _PATH_FIELDS if key in args})
                ret.add_path(path, k=k, **kwargs)
        return ret


__all__ = ["KPathContainer"]
