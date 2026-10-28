"""Named sets of links used to group and post-process network results."""

from __future__ import annotations

from typing import TypeAlias

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from ..loaders.monitored_links_sets_loader import MonitoredLinksSetsLoader

MonitoredLinksSetsType: TypeAlias = list[str]

__all__ = ["MonitoredLinksSetsModel", "MonitoredLinksSetsType"]


class MonitoredLinksSetsModel(BaseModel):
    """Hold the link identifiers belonging to each named links set."""

    def __init__(self, links_sets: MonitoredLinksSetsType | None = None):
        """Create an empty links set collection."""
        super().__init__()
        self._links_sets: MonitoredLinksSetsType = links_sets or []

    @property
    def monitored_links_sets(self) -> MonitoredLinksSetsType:
        """Links sets.

        Returns:
            A list of links set IDs.

        """
        return self._links_sets

    @classmethod
    def read(cls, kw_monitored_links_sets: InputType | None) -> MonitoredLinksSetsModel:
        """Read.

        Args:
            kw_monitored_links_sets: The parameters for reading the links sets.

        Returns:
            An instance of `MonitoredLinksSetsModel` containing the read links sets.

        """
        this = cls()
        if not bool(kw_monitored_links_sets):
            this.log.warning("No links sets source provided.")
            return this
        ret = MonitoredLinksSetsLoader.read(this.engine, params=kw_monitored_links_sets)
        if ret is not None and ret.df is not None:
            if ret.df.empty:
                monitored_links_sets = []
            else:
                monitored_links_sets = ret.df["id_set"].astype(str).tolist()
            this._links_sets = monitored_links_sets  # type: ignore
        else:
            raise ValueError("Failed to read links sets")

        return this

    def __str__(self) -> str:
        """Return the size of each links set."""
        link_sets = ", ".join(f"{k}" for k in self._links_sets)
        return f"{self.__class__.__name__}({link_sets})"
