from __future__ import annotations

from enum import Enum


class ActionPolicy(str, Enum):
    """Behaviour for duplicate, missing, or dependent entities."""

    RAISE = "raise"
    WARN = "warn"
    IGNORE = "ignore"
    REPLACE = "replace"
    SKIP = "skip"

    @classmethod
    def parse(cls, value: ActionPolicy | str) -> ActionPolicy:
        """Return an ``ActionPolicy`` from an enum value or string."""
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as exc:
            msg = "policy must be 'raise', 'warn', 'ignore', 'replace', or 'skip'"
            raise ValueError(msg) from exc


__all__ = ["ActionPolicy"]
