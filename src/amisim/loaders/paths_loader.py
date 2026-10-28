"""Loader of the computed paths."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..base.base_loader import BaseLoader, DataResultType
from .parsers import parse_list

__all__ = ["PathsLoader"]


class PathsLoader(BaseLoader):
    """Read and write the paths with their links, costs and flows."""

    field_definition: dict[str, Any] | None = {
        "source": {"mapping": "source", "dtype": "Int64", "required": True},
        "target": {"mapping": "target", "dtype": "Int64", "required": True},
        "t_start": {"mapping": "t_start", "dtype": "Int16", "required": True},
        "t_base": {"mapping": "t_base", "dtype": "Int16", "required": True},
        "t": {"mapping": "t", "dtype": "Int16", "required": True},
        "mode": {"mapping": "mode", "dtype": "str", "required": True},
        "tot_cost": {"mapping": "tot_cost", "dtype": "Float32", "required": True},
        "links": {"mapping": "links", "dtype": "str", "required": True, "parser": parse_list},
        "costs": {
            "mapping": "costs",
            "dtype": "str",
            "required": True,
            "parser": lambda s: parse_list(s, subtype=float),
        },
        "k": {"mapping": "k", "dtype": "Int8", "required": True},
        "path_flow": {"mapping": "path_flow", "dtype": "Float32", "required": True},
        "geometry": {"mapping": "geometry", "dtype": "geometry", "required": True},
    }
    additional_fields: dict[str, Any] | None = {}

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
        tmp = self.df.set_index(["source", "target"])
        other_tmp = other.df.set_index(["source", "target"])
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
