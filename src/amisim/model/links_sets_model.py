"""Named sets of links used to group and post-process network results."""

from __future__ import annotations

from typing import Any, TypeAlias

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from ..loaders.links_sets_loader import LinksSetsLoader

LinksSetsType: TypeAlias = dict[str, list[Any]]

__all__ = ["LinksSetsModel", "LinksSetsType"]


class LinksSetsModel(BaseModel):
    """Hold the link identifiers belonging to each named links set."""

    def __init__(self):
        """Create an empty links set collection."""
        super().__init__()
        self._links_sets: LinksSetsType = {}

    @property
    def links_sets(self) -> LinksSetsType:
        """Links sets.

        Returns:
            A dictionary where the keys are links set IDs and the values are lists of link IDs.

        """
        return self._links_sets

    def __getitem__(self, key: str) -> list[Any] | None:
        """Return the links of the given set."""
        if key not in self._links_sets:
            raise KeyError(f"Links set with key '{key}' not found.")
        return self._links_sets[key]

    def __setitem__(self, key: str, value: list[Any]) -> None:
        """Set the links of the given set."""
        self._links_sets[key] = value

    @classmethod
    def read(cls, kw_links_sets: InputType | None) -> LinksSetsModel:
        """Read.

        Args:
            engine: The engine used to read the links sets.
            kw_links_sets: The parameters for reading the links sets.

        Returns:
            An instance of `LinksSet` containing the read links sets.

        """
        this = cls()
        if not bool(kw_links_sets):
            this.log.warning("No links sets source provided.")
            return this
        ret = LinksSetsLoader.read(this.engine, params=kw_links_sets)
        if ret is not None and ret.df is not None:
            if ret.df.empty:
                links_sets = {}
            else:
                links_sets = ret.df.groupby("id_set").agg(cum=("id_link", list)).to_dict()["cum"]
                links_sets = {str(k): v for k, v in links_sets.items()}
            this._links_sets = links_sets  # type: ignore
        else:
            raise ValueError("Failed to read links sets")

        return this

    def __str__(self) -> str:
        """Return the size of each links set."""
        link_sets = ", ".join(f"{k}:{len(v)}" for k, v in self._links_sets.items())
        return f"LinksSet({link_sets})"
