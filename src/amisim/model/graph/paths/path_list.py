from __future__ import annotations

from collections.abc import Generator, Hashable
from typing import Any

from .path import Path
from .path_container import PathContainer

Numeric = int | float


class PathList(PathContainer):
    """Dictionary-backed collection with at most one path per path key."""

    def __init__(self, **kwargs: Any) -> None:
        """Create an empty path list."""
        self._paths: dict[Hashable, Path] = {}

    def add_path(self, to_add: Path, **kwargs: Any) -> None:
        """Add or replace a path by its canonical key."""
        self._paths[to_add.key()] = to_add    

    def clear(self, new_paths: PathContainer | None = None) -> None:
        self._paths.clear()
        if new_paths is not None:
            for path in new_paths.all_paths():
                self.add_path(path)

    def get_path(
        self,
        source: Hashable,
        target: Hashable | None = None,
        t_start: Numeric | None = 0,
        mode: str | None = None,
        **kwargs: Any,
    ) -> Path | None:
        """Return one path by key, or ``None`` when missing."""
        return self._paths.get(Path.calc_key(source=source, target=target, t_start=t_start, mode=mode))

    def all_paths(self, **kwargs: Any) -> Generator[Path, None, None]:
        """Yield all paths in insertion order."""
        yield from self._paths.values()  # type: ignore

    def n_paths(self, **kwargs: Any) -> int:
        """Count paths in the list."""
        return len(self._paths)  # type: ignore


__all__ = ["PathList"]
