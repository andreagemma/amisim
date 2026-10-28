"""Loader of the network links."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..base.base_loader import BaseLoader, DataResultType
from .parsers import parse_set

__all__ = ["LinksLoader"]


class LinksLoader(BaseLoader):
    """Read and combine the link records, keyed by origin and destination node."""

    field_definition: dict[str, Any] | None = {
        "id": {"mapping": "id", "dtype": "Int64", "required": True, "default": "autoincrement"},
        "from_node": {"mapping": "from_node", "dtype": "Int64", "required": True},
        "to_node": {"mapping": "to_node", "dtype": "Int64", "required": True},
        "v0": {"mapping": "v0", "dtype": "Float32", "required": True},
        "connector": {"mapping": "connector", "dtype": "bool", "required": True},
        "lanes": {"mapping": "lanes", "dtype": "Float32", "required": True},
        "alpha": {"mapping": "alpha", "dtype": "Float32", "required": False, "default": 1.6},
        "rcr": {"mapping": "rcr", "dtype": "Float32", "required": False, "default": 30},
        "capacity": {"mapping": "capacity", "dtype": "Float32", "required": True},
        "length": {"mapping": "length", "dtype": "Float32", "required": True},
        "modes": {"mapping": "mode", "dtype": "str", "required": True, "parser": parse_set},
        "geometry": {"mapping": "geometry", "dtype": "geometry", "required": True},
        "vdf": {"mapping": "vdf", "dtype": "str", "required": False},
        "vdf_a": {"mapping": "vdf_a", "dtype": "Float32", "required": False},
        "vdf_b": {"mapping": "vdf_b", "dtype": "Float32", "required": False},
        "vdf_c": {"mapping": "vdf_c", "dtype": "Float32", "required": False},
        "vdf_d": {"mapping": "vdf_d", "dtype": "Float32", "required": False},
        "vdf_e": {"mapping": "vdf_e", "dtype": "Float32", "required": False},
        "vdf_f": {"mapping": "vdf_f", "dtype": "Float32", "required": False},
    }
    additional_fields: dict[str, Any] | None = {
        "t0": {"mapping": "t0", "dtype": "Float32", "override": False, "value": "length / v0 * 60"},
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
        if self.df is None:
            self.df = other.df.copy() if other.df is not None else None
            return self
        if other.df is None:
            return self
        tmp = self.df.set_index(["from_node", "to_node"])
        other_tmp = other.df.set_index(["from_node", "to_node"])
        tmp[tmp.index.isin(other_tmp.index)] = other_tmp.loc[tmp.index.isin(other_tmp.index)]
        new_rows = other_tmp[~other_tmp.index.isin(tmp.index)]
        self.df = pd.concat([tmp, new_rows]).reset_index()
        return self

    def __isub__(self, other: BaseLoader) -> BaseLoader:
        # rimuove le righe presenti in other dal DataFrame corrente
        """Merge `other` into this loader by subtracting its rows.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        if self.df is None:
            self.df = other.df.copy() if other.df is not None else None
            return self
        if other.df is None:
            return self
        tmp = self.df.set_index(["from_node", "to_node"])
        other_tmp = other.df.set_index(["from_node", "to_node"])
        tmp = tmp[~tmp.index.isin(other_tmp.index)]
        self.df = tmp.reset_index()
        return self

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
