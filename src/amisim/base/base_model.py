from __future__ import annotations

from .base_class import BaseClass


class BaseModel(BaseClass):
    """Common base class shared by the AMISim models."""

    def __init__(self, **kwargs):
        """Initialize the base model with optional keyword arguments.

        Args:
            **kwargs: Extra arguments forwarded to the parent class.
        """
        super().__init__(**kwargs)
