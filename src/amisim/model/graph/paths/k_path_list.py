from __future__ import annotations

from collections.abc import Generator, Hashable
from typing import Any

from .k_path_container import KPathContainer
from .path import Path
from .path_container import PathContainer

Numeric = int | float


class KPathList(KPathContainer):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._paths: dict[Hashable, list[Path]] = {}
        self._ull: dict[Hashable, list[Path]] = {}

    def clear(self, new_paths: PathContainer | None = None) -> None:
        self._paths.clear()
        self._ull.clear()
        if new_paths is not None:
            for path in new_paths.all_paths():
                self.add_path(path)

    def add_path(self, to_add: Path, k: int | None = None, **kwargs: Any):
        links_key = tuple(to_add.links)
        to_add.links = self._ull.setdefault(links_key, to_add.links)
        key = to_add.key()
        paths: list[Path | None] = self._paths.setdefault(key, [])  
        if k is None:
            paths.append(to_add)  # type: ignore
            to_add.k = len(paths) - 1
        else:
            paths.extend([None] * (k + 1 - len(paths))) if len(paths) < k + 1 else paths  # type: ignore
            paths[k] = to_add
            to_add.k = k


    def filter(
        self,
        source: Hashable | None = None,
        target: Hashable | None = None,
        t_start: Numeric | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> Generator[Path, None, None]:
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
            yield from self._paths.get(Path.calc_key(source=source, target=target, t_start=t_start, mode=mode), [])

    def get_path(
        self,
        source: Hashable,
        target: Hashable,
        t_start: Numeric | None = None,
        mode: str | None = None,
        k: int = 0,
        **kwargs: Any,
    ) -> Path | None:
        assert t_start is not None, "t_start must be specified"
        paths = self._paths.get(Path.calc_key(source=source, target=target, t_start=t_start, mode=mode))
        if paths and len(paths) > k:
            return paths[k]
        else:
            return None

    def all_paths(self, **kwargs: Any) -> Generator[Path]:
        for paths in self._paths.values():
            if len(paths)>0:
                yield from paths

    def all_kpaths(self, **kwargs: Any) -> Generator[tuple[tuple[Hashable, Hashable, Numeric, str | None], list[Path]]]:
        for paths in self._paths.values():
            if len(paths)>0:
                p = paths[0]
                yield ((p.source, p.target, p.t_start, p.mode), paths)

    def n_paths(self, **kwargs: Any) -> int:
        n = 0
        for paths in self._paths.values():
            n += len(paths)
        return n
    
    def empty(self) -> bool:
        if len(self._paths) == 0:
            return True
        return all(len(paths) == 0 for paths in self._paths.values())


    def n_unique_paths(self, **kwargs: Any) -> int:
        return len(self._ull)

    def max_k(self, **kwargs: Any) -> int:
        return max((len(paths) for paths in self._paths.values()), default=0)


__all__ = ["KPathList"]
