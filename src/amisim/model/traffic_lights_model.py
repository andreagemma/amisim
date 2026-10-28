"""Named sets of links used to group and post-process network results."""

from __future__ import annotations

from typing import Any, TypeAlias

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from ..loaders.traffic_lights_loader import TrafficLightsLoader

TrafficLightsType: TypeAlias = list[dict[str, Any]]

__all__ = ["TrafficLightsModel", "TrafficLightsType"]


class TrafficLightsModel(BaseModel):
    """Hold the traffic light identifiers belonging to each named traffic light set."""

    def __init__(self, traffic_lights: TrafficLightsType | None = None):
        """Create an empty links set collection."""
        super().__init__()
        self._traffic_lights: TrafficLightsType = traffic_lights if traffic_lights is not None else []

    @property
    def traffic_lights(self) -> TrafficLightsType:
        """Links sets.

        Returns:
            A list of dictionaries, each representing a traffic light.

        """
        return self._traffic_lights

    @classmethod
    def read(cls, kw_traffic_lights: InputType | None) -> TrafficLightsModel:
        """Read.

        Args:
            engine: The engine used to read the traffic lights.
            kw_traffic_lights: The parameters for reading the traffic lights.

        Returns:
            An instance of `TrafficLightsModel` containing the read traffic lights.

        """
        this = cls()
        if not bool(kw_traffic_lights):
            this.log.warning("No traffic lights source provided.")
            return this
        ret = TrafficLightsLoader.read(this.engine, params=kw_traffic_lights)
        if ret is not None and ret.df is not None:
            if ret.df.empty:
                traffic_lights = []
            else:
                traffic_lights = ret.df.to_dict(orient="records")
            this._traffic_lights = traffic_lights  # type: ignore
        else:
            raise ValueError("Failed to read traffic lights")

        return this

    def __str__(self) -> str:
        """Return the number of traffic lights."""
        return f"TrafficLights(count={len(self._traffic_lights)})"
