"""Parser for AMISim execution parameters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dictparser import DictParser

__all__ = ["ParamsParser"]


class ParamsParser(DictParser):
    """Read execution parameters from a file path.

    Args:
        params_path: Path to the JSON or YAML parameters file.
    """

    def __init__(
        self,
        params_or_path: str
        | Path
        | dict[str, Any]
        | DictParser
        | ParamsParser
        | None
        | list[str | Path | dict[str, Any] | DictParser | ParamsParser] = None,
    ) -> None:
        """Initialize the parser with the parameters file."""
        if not isinstance(params_or_path, (list, tuple)):
            super().__init__(params_or_path)
        else:
            for i, item in enumerate(params_or_path):
                if i == 0:
                    super().__init__(item)
                else:
                    self.update(item)

        if self.get("include") is not None:
            if isinstance(self.get("include"), list):
                for include_file in self.get("include"):
                    include_path = self.folder / include_file.format(**self.params)
                    self.update(include_path)
