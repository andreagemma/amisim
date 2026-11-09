from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from collections.abc import Generator, Hashable
from pathlib import Path as FilePath
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiLineString

from ..graphs.graph import Graph
from ..utils import make_inside_checker, multiline_to_line
from .path import Path

Numeric = int | float


_PATH_FIELDS = ("source", "target", "t_start", "links", "costs", "tot_cost", "mode", "t_base", "path_flow")


class PathContainer(ABC):
    """Abstract base class for path collections."""

    def __init__(self) -> None:
        """Create an empty path container with optional metadata."""

    def add_path(self, to_add: Path, **kwargs: Any) -> None:
        """Add one path to the container."""
        raise NotImplementedError

    def get_path(
        self,
        source: Hashable,
        target: Hashable | None = None,
        t_start: Numeric | None = 0,
        mode: str | None = None,
        **kwargs: Any,
    ) -> Path | None:
        """Return the first matching path, or None if no match is found."""
        for p in self.filter(source=source, target=target, t_start=t_start, mode=mode, **kwargs):
            return p
        return None

    @abstractmethod
    def all_paths(self, **kwargs: Any) -> Generator[Path, None, None]:
        """Yield all paths in the container."""
        raise NotImplementedError
    
    def merge(self, to_add: Path | PathContainer | list[Path], **kwargs: Any) -> None:
        """Merge one path or another container into this container."""
        if isinstance(to_add, Path):
            self.add_path(to_add, **kwargs)
        elif isinstance(to_add, PathContainer):  # type: ignore
            for path in to_add.all_paths(**kwargs):
                self.add_path(path)
        elif isinstance(to_add, list):  # pyright: ignore[reportUnnecessaryIsInstance]
            for path in to_add:
                self.add_path(path, **kwargs)
        elif hasattr(to_add, "all_paths"):  # pyright: ignore[reportUnnecessaryIsInstance]
            for path in to_add.all_paths(**kwargs):
                p = Path(
                    source=path["source"] if isinstance(path, dict) else path.source,
                    target=path["target"] if isinstance(path, dict) else path.target,
                    t_start=path["t_start"] if isinstance(path, dict) else path.t_start,
                    links=path["links"] if isinstance(path, dict) else path.links,
                    costs=path["costs"] if isinstance(path, dict) else path.costs,
                    tot_cost=None,
                    mode=path["mode"] if isinstance(path, dict) else path.mode,
                    t_base=path["t_base"] if isinstance(path, dict) else path.t_base,
                    path_flow=path["path_flow"] if isinstance(path, dict) else path.path_flow,
                    k=path["k"] if isinstance(path, dict) else path.k,
                )
                self.add_path(p, **kwargs)
        else:
            msg = f"merge is not implemented for {type(to_add)!r}"
            raise NotImplementedError(msg)                

    def clear(self, new_paths: PathContainer | None = None) -> None:
        raise NotImplementedError

    def get_sources(
        self,
        target: Hashable | None = None,
        t_start: Numeric | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> tuple[Hashable, ...]:
        """Return source labels matching the optional filters."""
        return tuple(set(p.source for p in self.filter(target=target, t_start=t_start, mode=mode, **kwargs)))

    def get_targets(
        self,
        source: Hashable | None = None,
        t_start: Numeric | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> tuple[Hashable, ...]:
        return tuple(set(p.target for p in self.filter(source=source, t_start=t_start, mode=mode, **kwargs)))

    def get_t_starts(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> tuple[Numeric, ...]:
        return tuple(set(p.t_start for p in self.filter(source=source, target=target, mode=mode, **kwargs)))
    
    def get_ts(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> tuple[Numeric, ...]:
        return tuple(set(p.t for p in self.filter(source=source, target=target, mode=mode, **kwargs)))

    def get_modes(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        t_start: Numeric | None = None,
        **kwargs: Any,
    ) -> tuple[Hashable, ...]:
        """Return mode labels matching the optional filters."""
        return tuple(set(p.mode for p in self.filter(source=source, target=target, t_start=t_start, **kwargs)))

    def filter(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        t_start: Numeric | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> Generator[Path, None, None]:
        """Yield all k-ranked paths matching one canonical key."""
        for p in self.all_paths():
            if source is not None and p.source != source:
                continue
            if target is not None and p.target != target:
                continue
            if t_start is not None and p.t_start != t_start:
                continue
            if mode is not None and p.mode != mode:
                continue
            yield p



    def counts_tot_links(self, **kwargs: Any) -> int:
        """Count the total number of link occurrences in all matching paths."""
        return sum(len(path.links) for path in self.all_paths(**kwargs))

    def counts_link(self, id_link: Hashable, **kwargs: Any) -> int:
        """Count occurrences of ``id_link`` in all matching paths."""
        return sum(path.counts_link(id_link) for path in self.all_paths(**kwargs))

    def n_paths(self, **kwargs: Any) -> int:
        """Count all matching paths."""
        return sum(1 for _ in self.all_paths(**kwargs))

    def empty(self) -> bool:
        return self.n_paths() == 0
    
    def save(self, filename: str | FilePath) -> None:
        """Serialize the container to ``filename`` using dill."""
        import dill  # type: ignore

        with open(filename, "wb") as file:
            dill.dump(self, file, dill.HIGHEST_PROTOCOL)  # type: ignore

    @staticmethod
    def load(filename: str | FilePath) -> PathContainer:
        """Load a serialized path container from ``filename``."""
        import dill  # type: ignore

        with open(filename, "rb") as file:
            return dill.load(file)  # type: ignore

    def to_pandas(
        self, G: Graph, crs_link: str = "EPSG:4326", t: Numeric | None = None
    ) -> pd.DataFrame | gpd.GeoDataFrame:
        df_paths: pd.DataFrame = pd.DataFrame(
            path.to_dict() for path in self.all_paths() if t is None or path.t == t
        )
        if df_paths.empty:
            df_paths = gpd.GeoDataFrame(df_paths, geometry=[], crs=crs_link)
            return df_paths
        _link: dict[str, Any] = next(G.get_all_links())
        for geom in ("geom", "geometry"):
            if geom in _link:
                df_paths[geom] = [  # type: ignore
                    MultiLineString(
                        [
                            multiline_to_line(link.get(geom))
                            for l_idx in links
                            if (link := G.get_link(l_idx)) is not None
                        ]  # type: ignore
                    )
                    for links in df_paths["links"]
                ]
                df_paths = gpd.GeoDataFrame(df_paths, geometry=geom, crs=crs_link)
                return df_paths
        return df_paths

    @classmethod
    def from_pandas(
        cls, df: pd.DataFrame | dict[str, Any] | list[dict[str, Any]], **kwargs: dict[str, Any]
    ) -> PathContainer:
        ret = cls()
        _df: pd.DataFrame = df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
        for _, (_, row) in enumerate(_df.iterrows()):
            args = {str(key): value for key, value in dict(row.to_dict()).items()}
            path = Path(**{key: args[key] for key in _PATH_FIELDS if key in args})
            ret.add_path(path, **kwargs)
        return ret

        
    def copy(self) -> PathContainer:
        """Return a shallow copy of the path container."""
        return copy.deepcopy(self)

    def cut_time_slice(
        self,
        time_start: int | None = None,
        time_end: int | None = None,
        rebase: int | None = None,
        inplace: bool = True,
        normalize_at: int = 1440,
        shift: bool = True,
        offset: int = 0,
    ) -> PathContainer:
        other: PathContainer = self.__class__()
        is_inside = make_inside_checker(time_start=time_start, time_end=time_end, normalize_at=normalize_at)
        l_paths: list[Path] = []
        for path in self.all_paths():
            path = path if inplace else path.copy()
            t = path.t
            if is_inside(t):
                if rebase is not None:
                    path.t_start += path.t_base - rebase + offset
                    path.t += offset
                    path.t_base = rebase
                l_paths.append(path)
        if rebase is not None and shift:
            min_t_start = min(path.t_start for path in l_paths) if l_paths else 0
            if min_t_start != 0:
                for path in l_paths:
                    path.t_start -= min_t_start
                    path.t -= min_t_start
        for path in l_paths:
            other.add_path(path)
        if inplace:
            self.clear(new_paths=other)
            return self
        else:
            return other

__all__ = ["PathContainer"]
