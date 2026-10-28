"""Named sets of network events used to group and post-process network results."""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from typing import Any, TypeAlias

import pandas as pd

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from ..loaders.events_loader import EventsLoader
from .simulation_interval import SimulationDatetime

EventsType: TypeAlias = dict[str, list[dict[str, Any]]]

__all__ = ["EventsModel", "EventsType"]


class EventsModel(BaseModel):
    """Hold the network events belonging to each detector."""

    def __init__(self, events: EventsType | None = None):
        """Create an empty events collection."""
        super().__init__()
        self._events: EventsType = events or {}

    @property
    def events(self) -> EventsType:
        """Events.

        Returns:
            A dictionary where the keys are event types and the values are lists of events.

        """
        return self._events

    @classmethod
    def read(cls, kw_events: InputType | None) -> EventsModel:
        """Read.

        Args:
            kw_events: The parameters for reading the events.

        Returns:
            An instance of `EventsModel` containing the read events.

        """
        this = cls()
        if not bool(kw_events):
            this.log.warning("No events source provided.")
            return this
        ret = EventsLoader.read(this.engine, params=kw_events)
        if ret is None or ret.df is None:
            this._events = {}
            return this
        _events = defaultdict(list)
        for row in ret.df.to_dict(orient="records"):
            id_links = this._get_links_sets(row["id_link_set"])
            try:
                if pd.isna(row["params"]):
                    params = None
                else:
                    if not isinstance(row["params"], dict):
                        params = json.loads(row["params"])
                    else:
                        params = row["params"]
            except:
                raise Exception(f"Failed to interpret event parameters:\n{row}")
            event = {
                "arc_list": id_links,
                "type": row["type"],
                "start": SimulationDatetime(row["start"]).minutes_from_midnight(),
                "end": SimulationDatetime(row["end"]).minutes_from_midnight(),
                "params": params,
            }
            row.update(event)
            _events[event["type"]].append(row)
        this._events = dict(_events)
        return this

    def __str__(self) -> str:
        """Return the number of events."""
        return f"Events(#{len(self._events)})"

    def _get_links_sets(self, name: str):
        assert self.app is not None, "The app context must be available"
        ws = self.app.workspace
        assert ws.graph_model is not None, "The events model must be available"
        assert ws.graph_model.graph is not None, "The graph must be available"
        assert ws.links_sets_model is not None, "The links sets model must be available"

        links_sets_model = ws.links_sets_model
        if pd.isna(name) or not name:
            return list(ws.graph_model.graph.get_all_links_idx())

        id_links = []
        try:
            if isinstance(name, str):
                if name.isdigit():
                    id_links = [int(name)]
                else:
                    id_links = links_sets_model.links_sets.get(name, [])
            else:
                tmp = ast.literal_eval(str(name))
                if isinstance(tmp, (tuple, list)):
                    id_links = list(tmp)
                elif isinstance(tmp, str):
                    id_links = links_sets_model.links_sets.get(tmp, [])
        except:
            try:
                id_links = links_sets_model.links_sets.get(name, [])
            except:
                raise Exception(f"The links_sets {name} could not be identified")
        if len(id_links) == 0:
            self.log.warning(f"The links_sets {name} is empty")
        return id_links
