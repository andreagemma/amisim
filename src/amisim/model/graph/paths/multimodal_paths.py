from __future__ import annotations

from collections.abc import Generator, Hashable
from typing import Any

from .k_path_container import KPathContainer
from .k_path_list import KPathList
from .path import Path
from .path_container import PathContainer

Numeric = int | float


class MultimodalPaths(KPathContainer):
    """Dictionary-backed collection with multiple k-ranked paths per key."""

    def __init__(self, **kwargs: Any) -> None:
        """Create an empty k-path list."""
        super().__init__(**kwargs)
        self._paths: dict[str, KPathList] = {}

    def clear(self, new_paths: PathContainer | None = None) -> None:
        self._paths.clear()        
        if new_paths is not None:
            if isinstance(new_paths, MultimodalPaths):
                self._paths.update(new_paths._paths)
            elif isinstance(new_paths, PathContainer):
                for path in new_paths.all_paths():
                    self.add_path(path)    

    @property
    def modes(self) -> list[str]:
        return list(self._paths.keys())

    def add_path(self, to_add: Path, k: int | None = None, **kwargs: Any) -> None:
        """Add a path at the next or selected k position."""
        if paths := self._paths.get(to_add.mode):  # type: ignore
            paths.add_path(to_add, k=k)
        else:
            paths = KPathList()
            paths.add_path(to_add, k=k)
            self._paths[to_add.mode] = paths  # type: ignore

    def get_sources(
        self,
        target: Hashable | None = None,
        t_start: Numeric | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> tuple[Hashable, ...]:
        """Return source labels matching the optional filters."""
        if mode is not None:
            if mode in self._paths:
                return self._paths[mode].get_sources(target=target, t_start=t_start, mode=mode)
            return tuple()
        else:
            ret = []  # type: ignore
            for paths in self._paths.values():
                ret.extend(paths.get_sources(target=target, t_start=t_start, mode=mode))  # type: ignore
            return tuple(ret)  # type: ignore

    def get_targets(
        self,
        source: Hashable | None = None,
        t_start: Numeric | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> tuple[Hashable, ...]:
        """Return target labels matching the optional filters."""
        if mode is not None:
            if mode in self._paths:
                return self._paths[mode].get_targets(source=source, t_start=t_start, mode=mode)
            return tuple()
        else:
            ret = []  # type: ignore
            for paths in self._paths.values():
                ret.extend(paths.get_targets(source=source, t_start=t_start, mode=mode))  # type: ignore
            return tuple(ret)  # type: ignore

    def get_t_starts(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> tuple[Numeric, ...]:
        """Return departure times matching the optional filters."""
        if mode is not None:
            if mode in self._paths:
                return self._paths[mode].get_t_starts(source=source, target=target, mode=mode)
            return tuple()
        else:
            ret = []  # type: ignore
            for paths in self._paths.values():
                ret.extend(paths.get_t_starts(source=source, target=target, mode=mode))  # type: ignore
            return tuple(ret)  # type: ignore

    def get_ts(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> tuple[Numeric, ...]:
        """Return departure times matching the optional filters."""
        if mode is not None:
            if mode in self._paths:
                return self._paths[mode].get_ts(source=source, target=target, mode=mode)
            return tuple()
        else:
            ret = []  # type: ignore
            for paths in self._paths.values():
                ret.extend(paths.get_ts(source=source, target=target, mode=mode))  # type: ignore
            return tuple(ret)  # type: ignore

    def get_modes(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        t_start: Numeric | None = None,
        **kwargs: Any,
    ) -> tuple[Hashable, ...]:
        """Return mode labels matching the optional filters."""
        if source is None and target is None and t_start is None:
            return tuple(self._paths.keys())
        ret = set()  # type: ignore
        for mode, kpaths in self._paths.items():
            for p in kpaths.filter(source=source, target=target, t_start=t_start, mode=mode):
                ret.add(mode)
                break
        return tuple(ret)

    def filter(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        t_start: Numeric | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> Generator[Path, None, None]:
        """Yield all k-ranked paths matching one canonical key."""
        if mode is None or source is None or target is None or t_start is None:
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
        else:
            modes_paths: KPathList | None = self._paths.get(mode)
            if modes_paths is None:
                return
            yield from modes_paths.filter(source=source, target=target, t_start=t_start, mode=mode)

    def get_path(
        self,
        source: Hashable,
        target: Hashable,
        t_start: Numeric,
        mode: str | None = None,
        k: int = 0,
        **kwargs: Any,
    ) -> Path | None:
        """Return one path by canonical key and k position."""
        del kwargs
        if mode is None:
            return None
        paths: KPathList | None = self._paths.get(mode)
        if paths is None:
            return None
        lpaths: list[Path] = list(paths.filter(source=source, target=target, t_start=t_start, mode=mode))
        if len(lpaths) > k:
            return lpaths[k]
        return None

    def all_paths(self, **kwargs: Any) -> Generator[Path, None, None]:
        """Yield all non-empty stored paths in insertion order."""
        for kpaths in self._paths.values():
            yield from kpaths.all_paths()

    def all_kpaths(
        self,
        **kwargs: Any,
    ) -> Generator[tuple[tuple[Hashable, Hashable, Numeric, str | None], list[Path]], None, None]:
        """Yield each canonical key with its non-empty path list."""
        for kpaths in self._paths.values():
            yield from kpaths.all_kpaths()

    def empty(self) -> bool:
        """Check if there are no stored paths."""
        if len(self._paths) == 0:
            return True
        return all(kpaths.empty() for kpaths in self._paths.values())

    def n_paths(self, **kwargs: Any) -> int:
        """Count all non-empty stored paths."""
        s = 0
        for _ in self.all_paths():
            s += 1
        return s

    def n_unique_paths(self, **kwargs: Any) -> int:
        """Count all unique non-empty stored paths."""
        s = 0
        for _, paths in self._paths.items():
            s += paths.n_unique_paths()
        return s

    def max_k(self, **kwargs: Any) -> int:
        """Return the maximum number of k slots stored for any key."""
        return max((kpaths.max_k() for kpaths in self._paths.values()), default=0)  # type: ignore

    def get_by_mode(self, mode: str, create_if_missing: bool = False) -> KPathList | None:
        """Return all available mode labels."""
        if create_if_missing and mode not in self._paths:
            self._paths[mode] = KPathList()
        return self._paths.get(mode)

    def set_by_mode(self, mode: str, kpaths: KPathList) -> None:
        """Set the paths for a specific mode."""
        self._paths[mode] = kpaths

    def to_str(self) -> str:
        """Return the number of paths per mode."""
        m_paths = {m: self.get_by_mode(m) for m in self.modes}
        paths = ", ".join(f"{m}:{p.n_paths()}" for m, p in m_paths.items() if p is not None)
        return f"Paths({paths})"


__all__ = ["MultimodalPaths"]
