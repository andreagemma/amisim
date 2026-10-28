"""Loader of the network links."""

from __future__ import annotations

from typing import Any

from ..base.base_loader import BaseLoader, DataResultType
from .parsers import parse_json

__all__ = ["TrafficLightsLoader"]


class TrafficLightsLoader(BaseLoader):
    """Read and combine the traffic light records, keyed by origin and destination node."""

    field_definition: dict[str, Any] | None = {
        "id": {"mapping": "id", "dtype": "Int64", "required": True},
        "cycle": {"mapping": "cycle", "dtype": "Float32", "required": True},
        "offset": {"mapping": "offset", "dtype": "Float32", "required": True},
        "phases": {"mapping": "phases", "dtype": "str", "required": True, "parser": parse_json},
    }

    def __init__(self):
        """Create the loader with its default field definition."""
        super().__init__()

    @classmethod
    def parse(cls, source: DataResultType) -> BaseLoader:
        """Parse.

        Args:
            source: Dataframe to wrap into the loader.

        Returns:
            The loader holding the parsed dataframe.

        """
        ret = cls()
        ret.df = source
        return ret

    def __iadd__(self, other: BaseLoader) -> BaseLoader:
        # sostituisce i valori esistenti con quelli di other
        # e aggiunge le nuove righe da other
        """Merge `other` into this loader by adding its rows.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        raise NotImplementedError("The __iadd__ method must be implemented by the subclass.")

    def __isub__(self, other: BaseLoader) -> BaseLoader:
        # rimuove le righe presenti in other dal DataFrame corrente
        """Merge `other` into this loader by subtracting its rows.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        raise NotImplementedError("The __isub__ method must be implemented by the subclass.")

    def __imul__(self, other: BaseLoader) -> BaseLoader:
        """Merge `other` into this loader by multiplying its values.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        raise NotImplementedError("The __imul__ method must be implemented by the subclass.")

    def __itruediv__(self, other: BaseLoader) -> BaseLoader:
        """Merge `other` into this loader by dividing its values.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        raise NotImplementedError("The __itruediv__ method must be implemented by the subclass.")
