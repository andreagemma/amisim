"""Named sets of links used to group and post-process network results."""

from __future__ import annotations

from typing import TypeAlias

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from ..loaders.detectors_loader import DetectorsLoader

DetectorsType: TypeAlias = dict[int, int]

__all__ = ["DetectorsModel", "DetectorsType"]


class DetectorsModel(BaseModel):
    """Hold the link identifiers belonging to each detector."""

    def __init__(self, detectors: DetectorsType | None = None):
        """Create an empty links set collection."""
        super().__init__()
        self._detectors: DetectorsType = detectors if detectors is not None else {}

    @property
    def detectors(self) -> DetectorsType:
        """Detectors.

        Returns:
            A dictionary where the keys are detector IDs and the values are link IDs.

        """
        return self._detectors

    def __getitem__(self, key: int) -> int | None:
        """Return the link ID of the given detector."""
        if key not in self._detectors:
            raise KeyError(f"Detector with key '{key}' not found.")
        return self._detectors.get(key)

    def __setitem__(self, key: int, value: int) -> None:
        """Set the link ID of the given detector."""
        self._detectors[key] = value

    @classmethod
    def read(cls, kw_detectors: InputType | None) -> DetectorsModel:
        """Read.

        Args:
            kw_detectors: The parameters for reading the detectors.

        Returns:
            An instance of `DetectorsModel` containing the read detectors.

        """
        this = cls()
        if not bool(kw_detectors):
            this.log.warning("No detectors source provided.")
            return this
        ret = DetectorsLoader.read(this.engine, params=kw_detectors)
        if ret is not None and ret.df is not None:
            if ret.df.empty:
                detectors = {}
            else:
                detectors = ret.df.set_index("id_set")["id_link"].to_dict()
            this._detectors = detectors  # type: ignore
        else:
            raise ValueError("Failed to read detectors")

        return this

    def __str__(self) -> str:
        """Return the number of detectors."""
        return f"Detectors(#{len(self._detectors)})"
