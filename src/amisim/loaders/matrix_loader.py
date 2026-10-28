"""Loader of the origin-destination demand matrices."""

from __future__ import annotations

from typing import Any

from ..base.base_loader import BaseLoader, DataResultType

__all__ = ["MatrixLoader"]


class MatrixLoader(BaseLoader):
    """Read and combine the demand records in origin/destination/time form."""

    field_definition: dict[str, Any] | None = {
        "o": {"mapping": "o", "dtype": "Int64", "required": True},
        "d": {"mapping": "d", "dtype": "Int64", "required": True},
        "timestamp": {"mapping": "timestamp", "dtype": "Float32", "required": True},
        "value": {"mapping": "value", "dtype": "Float32", "required": True},
        "day_type": {"mapping": "day_type", "dtype": "string", "required": True, "default": "all"},
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
        # somma i valori di self.df e other.df basandosi sugli indici ["o", "d", "timestamp"]
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
        tmp = self.df.set_index(["o", "d", "timestamp", "day_type"])
        other_tmp = other.df.set_index(["o", "d", "timestamp", "day_type"])
        tmp = tmp.add(other_tmp, fill_value=0)
        self.df = tmp.reset_index()
        return self

    def __isub__(self, other: BaseLoader) -> BaseLoader:
        # sottrae i valori di other.df da self.df basandosi sugli indici ["o", "d", "timestamp"]
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
        tmp = self.df.set_index(["o", "d", "timestamp", "day_type"])
        other_tmp = other.df.set_index(["o", "d", "timestamp", "day_type"])
        tmp = tmp.sub(other_tmp, fill_value=0)
        self.df = tmp.reset_index()
        return self

    def __imul__(self, other: BaseLoader) -> BaseLoader:
        # moltiplica i valori di self.df per quelli di other.df basandosi sugli indici ["o", "d", "timestamp"]
        """Merge `other` into this loader by multiplying its values.

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
        tmp = self.df.set_index(["o", "d", "timestamp", "day_type"])
        other_tmp = other.df.set_index(["o", "d", "timestamp", "day_type"])
        tmp = tmp.mul(other_tmp, fill_value=0)
        self.df = tmp.reset_index()
        return self

    def __itruediv__(self, other: BaseLoader) -> BaseLoader:
        # divide i valori di self.df per quelli di other.df basandosi sugli indici ["o", "d", "timestamp"]
        """Merge `other` into this loader by dividing its values.

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
        tmp = self.df.set_index(["o", "d", "timestamp", "day_type"])
        other_tmp = other.df.set_index(["o", "d", "timestamp", "day_type"])
        tmp = tmp.div(other_tmp, fill_value=0)
        self.df = tmp.reset_index()
        return self
