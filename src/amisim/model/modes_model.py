"""Transport modes available in a workspace."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, TypeAlias

from pandas import isna

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from ..loaders.modes_loader import ModesLoader

ModeCode: TypeAlias = str
ModeType: TypeAlias = dict[str, Any]
ModesType: TypeAlias = dict[ModeCode, ModeType]
ModeCodesType: TypeAlias = set[str] | list[str]

__all__ = ["ModesModel", "ModesType", "ModeType", "ModeCode", "ModeCodesType"]


class ModesModel(BaseModel):
    """Hold the transport modes indexed by their code."""

    def __init__(self, other: ModesModel | ModesType | None = None):
        """Create an empty modes collection or initialize from another instance or dictionary."""
        super().__init__()
        self._modes: ModesType = {}
        if isinstance(other, ModesModel):
            self._modes = other.modes
        elif isinstance(other, dict):
            self._modes = other

    def copy(self) -> ModesModel:
        """Return a copy of the current modes collection."""
        return ModesModel(deepcopy(self._modes))

    @property
    def modes(self) -> ModesType:
        """Modes.

        Returns:
            A dictionary mapping each mode code to its attributes.

        """
        return self._modes

    @property
    def codes(self) -> ModeCodesType:
        """Return the set of mode codes."""
        return set(self._modes.keys())

    @property
    def eq_factors(self) -> dict[str, Any]:
        """Return the equilibrium factors for each mode."""
        return {code: attrs.get("eq_factor", 1) for code, attrs in self._modes.items()}

    def remove(self, *keys) -> ModesModel:
        """Remove the specified modes by their codes."""
        for key in keys:
            if key in self._modes:
                del self._modes[key]
        return self

    def retain(self, *keys) -> ModesModel:
        """Retain only the specified modes by their codes."""
        keys_set = set(keys)
        for key in list(self._modes.keys()):
            if key not in keys_set:
                del self._modes[key]
        return self

    def __getitem__(self, key: str) -> ModeType | None:
        """Return the attributes of the given mode."""
        if key not in self._modes:
            raise KeyError(f"Mode with key '{key}' not found.")
        return self._modes[key]

    def __setitem__(self, key: str, value: ModeType) -> None:
        """Set the attributes of the given mode."""
        self._modes[key] = value

    def parse(self, mode: set[str] | str | None) -> set[str]:
        """Resolve a mode specification into a set of mode codes.

        Args:
            mode: A set of codes, a single code, `"all"`, `"none"`, empty or
                `None` (all modes).

        Returns:
            The resolved set of mode codes.

        Raises:
            ValueError: If the code is not among the available modes.
        """
        if isinstance(mode, set):
            return mode
        mode = mode.strip().lower() if mode else ""
        if isna(mode) or mode == "":
            return set(self._modes.keys())
        elif mode in self._modes:
            return {mode}
        elif mode == "all":
            return set(self._modes.keys())
        elif mode == "none":
            return set()
        else:
            raise ValueError(f"Unknown mode: '{mode}'")

    @classmethod
    def read(cls, kw_modes: InputType | None) -> ModesModel:
        """Read.

        Args:
            engine: Engine used to read the modes.
            kw_modes: Parameters describing the modes source.

        Returns:
            An instance of `Modes` containing the read modes.

        Raises:
            ValueError: If the modes cannot be read.

        """
        this = cls()
        if not bool(kw_modes):
            this.log.warning("No modes source provided.")
            return this
        ret = ModesLoader.read(this.engine, params=kw_modes)
        if ret is not None and ret.df is not None:
            modes = ret.df.set_index("code").to_dict(orient="index")
            modes = {str(k): v for k, v in modes.items()}
            this._modes = modes  # type: ignore
        else:
            raise ValueError("Failed to read modes")

        return this

    def __str__(self) -> str:
        """Return the modes mapping as text."""
        if not self._modes:
            return "Modes({})"
        return f"Modes({str({k: v.get('eq_factor', 1) for k, v in self._modes.items()})})"
