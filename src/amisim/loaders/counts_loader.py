"""Loader of the transport modes."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..base.base_loader import BaseLoader, DataResultType

__all__ = ["CountsLoader"]


class CountsLoader(BaseLoader):
    """Read and combine the mode records, keyed by mode code."""

    field_definition: dict[str, Any] | None = {
        "id_detector": {"mapping": "id_detector", "dtype": "Int64", "required": True},
        "mode": {"mapping": "mode", "dtype": "string", "required": True},
        "day_type": {"mapping": "day_type", "dtype": "string", "required": True},
        "timestamp": {"mapping": "timestamp", "dtype": "string", "required": True},
        "counts": {"mapping": "counts", "dtype": "Float32", "required": True},
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
        tmp = self.df.set_index(["id_detector"])
        other_tmp = other.df.set_index(["id_detector"])
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
        if self.df is None or other.df is None:
            return self
        tmp = self.df.set_index(["id_detector"])
        other_tmp = other.df.set_index(["id_detector"])
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
