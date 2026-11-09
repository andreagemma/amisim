from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from copy import deepcopy
from enum import Enum
from math import atan2, degrees
from typing import Any

DEFAULT_TURN_ANGLES: tuple[float, float, float, float] = (30, 60, 120, 150)


class TurnType(Enum):
    """Semantic classification for the angle between two directed links."""

    STRAIGHT = "straight"
    SLIGHT_LEFT = "slight_left"
    SLIGHT_RIGHT = "slight_right"
    LEFT_ELBOW = "left_elbow"
    RIGHT_ELBOW = "right_elbow"
    SHARP_LEFT = "sharp_left"
    SHARP_RIGHT = "sharp_right"
    U_TURN = "u_turn"

    @staticmethod
    def parse(turn: str | TurnType) -> TurnType | None:
        """Parse a string value into a ``TurnType``."""
        if isinstance(turn, TurnType):
            return turn
        mapping = {
            "straight": TurnType.STRAIGHT,
            "slight_left": TurnType.SLIGHT_LEFT,
            "slight_right": TurnType.SLIGHT_RIGHT,
            "left_elbow": TurnType.LEFT_ELBOW,
            "right_elbow": TurnType.RIGHT_ELBOW,
            "sharp_left": TurnType.SHARP_LEFT,
            "sharp_right": TurnType.SHARP_RIGHT,
            "u_turn": TurnType.U_TURN,
        }
        return mapping.get(turn.lower())

    @staticmethod
    def _coerce(turn: str | TurnType) -> TurnType:
        # Internal helper: coerce.
        """Internal helper: coerce."""
        parsed = TurnType.parse(turn)
        if parsed is None:
            msg = f"unknown turn type: {turn!r}"
            raise ValueError(msg)
        return parsed

    @staticmethod
    def is_left_turn(
        turn_type: str | TurnType,
        min_type: str | TurnType = "slight_left",
    ) -> bool:
        """Return ``True`` when ``turn_type`` is at least the requested left turn."""
        turn = TurnType._coerce(turn_type)
        minimum = TurnType._coerce(min_type)
        if minimum not in {TurnType.SLIGHT_LEFT, TurnType.LEFT_ELBOW, TurnType.SHARP_LEFT}:
            msg = "min_type must be one of the left turn types"
            raise ValueError(msg)
        if minimum is TurnType.SLIGHT_LEFT:
            return turn in {TurnType.SLIGHT_LEFT, TurnType.LEFT_ELBOW, TurnType.SHARP_LEFT}
        if minimum is TurnType.LEFT_ELBOW:
            return turn in {TurnType.LEFT_ELBOW, TurnType.SHARP_LEFT}
        return turn == TurnType.SHARP_LEFT

    @staticmethod
    def is_right_turn(
        turn_type: str | TurnType,
        min_type: str | TurnType = "slight_right",
    ) -> bool:
        """Return ``True`` when ``turn_type`` is at least the requested right turn."""
        turn = TurnType._coerce(turn_type)
        minimum = TurnType._coerce(min_type)
        if minimum not in {TurnType.SLIGHT_RIGHT, TurnType.RIGHT_ELBOW, TurnType.SHARP_RIGHT}:
            msg = "min_type must be one of the right turn types"
            raise ValueError(msg)
        if minimum is TurnType.SLIGHT_RIGHT:
            return turn in {TurnType.SLIGHT_RIGHT, TurnType.RIGHT_ELBOW, TurnType.SHARP_RIGHT}
        if minimum is TurnType.RIGHT_ELBOW:
            return turn in {TurnType.RIGHT_ELBOW, TurnType.SHARP_RIGHT}
        return turn == TurnType.SHARP_RIGHT

    @staticmethod
    def is_u_turn(turn_type: str | TurnType) -> bool:
        """Return ``True`` when ``turn_type`` is a U-turn."""
        return TurnType._coerce(turn_type) == TurnType.U_TURN

    @staticmethod
    def is_straight(turn_type: str | TurnType) -> bool:
        """Return ``True`` when ``turn_type`` is straight."""
        return TurnType._coerce(turn_type) == TurnType.STRAIGHT

    @staticmethod
    def classify_turn(
        in_edge_geometry: Any,
        out_edge_geometry: Any,
        angles: Sequence[float] = DEFAULT_TURN_ANGLES,
    ) -> TurnType | None:
        """Classify the angle between an incoming and outgoing geometry."""
        if not in_edge_geometry or not out_edge_geometry:
            return None
        if len(angles) != 4:
            msg = "angles must contain four threshold values"
            raise ValueError(msg)

        incoming_coords = list(in_edge_geometry.coords)
        outgoing_coords = list(out_edge_geometry.coords)
        if len(incoming_coords) < 2 or len(outgoing_coords) < 2:
            return None

        x1, y1 = incoming_coords[-2]
        x2, y2 = incoming_coords[-1]
        x3, y3 = outgoing_coords[0]
        x4, y4 = outgoing_coords[1]

        incoming_vector = (x2 - x1, y2 - y1)
        outgoing_vector = (x4 - x3, y4 - y3)

        dot = incoming_vector[0] * outgoing_vector[0] + incoming_vector[1] * outgoing_vector[1]
        cross = incoming_vector[0] * outgoing_vector[1] - incoming_vector[1] * outgoing_vector[0]
        angle = degrees(atan2(cross, dot))
        absolute_angle = abs(angle)

        if absolute_angle < angles[0]:
            return TurnType.STRAIGHT
        if absolute_angle < angles[1]:
            return TurnType.SLIGHT_LEFT if angle > 0 else TurnType.SLIGHT_RIGHT
        if absolute_angle < angles[2]:
            return TurnType.LEFT_ELBOW if angle > 0 else TurnType.RIGHT_ELBOW
        if absolute_angle < angles[3]:
            return TurnType.SHARP_LEFT if angle > 0 else TurnType.SHARP_RIGHT
        return TurnType.U_TURN


class Turn(dict[Any, Any]):
    """Turn from one incoming link to one outgoing link."""

    def __init__(
        self,
        idx: Hashable,
        in_link: Hashable,
        out_link: Hashable,
        **kwargs: Any,
    ) -> None:
        """Create a turn with incoming and outgoing link identifiers."""
        super().__init__(**kwargs)
        self["idx"] = idx
        self["in_link"] = in_link
        self["out_link"] = out_link

    def combine(self, element: Turn, n_intervals_of_self: int, n_intervals_of_element: int) -> None:
        for key, new_value in element.items():
            if key not in self:
                if isinstance(new_value, list):
                    first = new_value[0] if new_value else None  # type: ignore
                    self[key] = [first] * n_intervals_of_self
                    self[key].extend(new_value)
                elif isinstance(new_value, tuple):
                    first = new_value[0] if new_value else None  # type: ignore
                    self[key] = tuple([first] * n_intervals_of_self)  # type: ignore
                    self[key] = self[key] + tuple(new_value)  # type: ignore
                else:
                    self[key] = new_value
            else:
                old_value = self.get(key)
                if old_value is not None:
                    if isinstance(old_value, list):
                        if isinstance(new_value, (tuple, list)):
                            old_value.extend(list(new_value))  # type: ignore
                        else:
                            old_value.extend([new_value] * n_intervals_of_element)  # type: ignore
                    elif isinstance(old_value, tuple):
                        if isinstance(new_value, (tuple, list)):
                            old_value = old_value + tuple(new_value)  # type: ignore
                        else:
                            old_value = old_value + tuple([new_value] * n_intervals_of_element)  # type: ignore
                        self[key] = old_value
                    else:
                        self[key] = new_value

    @property
    def idx(self) -> Hashable:
        """Turn identifier."""
        return self["idx"]

    @property
    def in_link(self) -> Hashable:
        """Incoming link identifier."""
        return self["in_link"]

    @property
    def out_link(self) -> Hashable:
        """Outgoing link identifier."""
        return self["out_link"]

    @staticmethod
    def classify_turn(
        in_edge_geometry: Any,
        out_edge_geometry: Any,
        angles: Sequence[float] = DEFAULT_TURN_ANGLES,
    ) -> TurnType | None:
        """Classify the angle between an incoming and outgoing geometry."""
        return TurnType.classify_turn(in_edge_geometry, out_edge_geometry, angles=angles)

    def copy(self) -> Turn:
        """Return a deep copy of the turn."""
        return deepcopy(self)

    def reset(self, name: str, value: Any | Callable[[Turn, int | None], Any]) -> None:
        if isinstance(self[name], (list, tuple)):
            n = len(self[name])
            if callable(value):
                self[name] = [value(self, i) for i in range(n)]
            elif isinstance(value, (list, tuple)):
                self[name] = value
            else:
                self[name] = [value for _ in range(n)]
        else:
            if callable(value):
                self[name] = value(self, None)
            else:
                self[name] = value


__all__ = ["Turn", "TurnType"]
