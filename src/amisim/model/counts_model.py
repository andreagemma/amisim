"""Named sets of links used to group and post-process network results."""

from __future__ import annotations

from typing import Hashable, TypeAlias

import pandas as pd

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from ..loaders.counts_loader import CountsLoader

CountsType: TypeAlias = pd.DataFrame

__all__ = ["CountsModel", "CountsType"]


class CountsModel(BaseModel):
    """Hold the link identifiers belonging to each detector."""

    def __init__(self, counts: CountsType | None = None):
        """Create an empty links set collection."""
        super().__init__()
        self._counts: CountsType = pd.DataFrame(columns=["id_detector", "mode", "day_type", "timestamp", "counts"])

    @property
    def counts(self) -> CountsType:
        """Counts.

        Returns:
            A DataFrame containing the counts data.

        """
        return self._counts

    @classmethod
    def read(cls, kw_counts: InputType | None) -> CountsModel:
        """Read.

        Args:
            kw_detectors: The parameters for reading the detectors.

        Returns:
            An instance of `CountsModel` containing the read detectors.

        """
        this = cls()
        if not bool(kw_counts):
            this.log.warning("No detectors source provided.")
            return this
        ret = CountsLoader.read(this.engine, params=kw_counts)
        if ret is not None and ret.df is not None:
            if ret.df.empty:
                counts = pd.DataFrame(columns=["id_detector", "mode", "day_type", "timestamp", "counts"])
            else:
                counts = ret.df
            this._counts = counts  # type: ignore
        else:
            raise ValueError("Failed to read counts")

        return this

    def __str__(self) -> str:
        """Return the number of detectors."""
        return f"Counts(#{len(self._counts)})"
