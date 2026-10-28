"""Origin-destination demand matrices, one per mode plus the equivalent one."""

from __future__ import annotations

from typing import Generator, Hashable, TypeAlias

from matrix import LabelsInput, Timestamp
from matrix import MatrixODTSparse as MatrixODT

from .modes_model import ModesModel

TimestampsType: TypeAlias = list[Timestamp]
MatricesType: TypeAlias = dict[str, MatrixODT]

__all__ = ["MultiModalDynamicMatrix", "MatrixODT", "TimestampsType", "LabelsInput", "Timestamp", "MatricesType"]


class MultiModalDynamicMatrix(dict):
    """Hold the demand matrices of each mode and their equivalent sum."""

    def __init__(
        self,
        rows: LabelsInput,
        cols: LabelsInput,
        timestamps: list[Timestamp] | set[Timestamp] | tuple[Timestamp, ...] | None = None,
        init: float | MatrixODT | dict[tuple[Hashable, Hashable, Timestamp], float] | None = None,
        copy: bool = False,
        mode: str | None = None,
    ) -> None:
        """Create an empty matrices collection."""
        super().__init__()
        self._rows = rows
        self._cols = cols
        self._timestamps = timestamps
        self._init = init
        self._mats: MatricesType = {}

    def has_mode(self, mode: str) -> bool:
        """Check if the given mode exists in the matrices."""
        return mode in self._mats

    @property
    def modes(self) -> list[str]:
        """Modes.

        Returns:
            The modes and their equivalence factors.

        """
        return list(self._mats.keys())

    def matrix_eq(self, modes: ModesModel) -> MatrixODT:
        """Compute the equivalent matrix based on the provided modes.

        Returns:
            The equivalent matrix obtained summing the modal matrices weighted
            by their `eq_factor`.

        Raises:
            ValueError: If the equivalent matrix has not been computed yet.

        """
        return self._calc_matrix_eq(modes)

    def get_od(self, mode: str, o: Hashable, d: Hashable, t: Timestamp) -> float:
        """Return the demand matrix of the given mode."""
        if mode not in self._mats:
            raise KeyError(f"MatrixODT with mode '{mode}' not found.")
        return self._mats[mode].get_od(o, d, t)

    def set_by_mode(self, key: str, value: MatrixODT) -> None:
        """Set the demand matrix for the given mode."""
        self._mats[key] = value

    def drop_modes(self, modes: list[str]) -> None:
        """Drop the specified modes from the matrices."""
        for mode in modes:
            if mode in self._mats:
                del self._mats[mode]

    def get_all_matrices(self) -> Generator[tuple[str, MatrixODT], None, None]:
        """Return all matrices as a dictionary keyed by mode."""
        yield from self._mats.items()

    def _calc_matrix_eq(self, modes: ModesModel) -> MatrixODT:
        # Internal helper: calc matrix eq.
        """Internal helper: calc matrix eq."""
        ret: MatrixODT | None = None
        if not self._mats:
            raise ValueError("No matrices loaded.")
        for key, mat in self._mats.items():
            eq_factor = modes.modes.get(key, {}).get("eq_factor", 1)
            if ret is None:
                ret = mat * eq_factor
            else:
                ret = ret + mat * eq_factor
        if ret is None:
            raise ValueError("No matching matrices found.")
        return ret

    def get_by_mode(self, mode: str, create_if_missing: bool = False) -> MatrixODT | None:
        """Return the matrix for the specified mode, or None if it doesn't exist.

        Args:
            mode: The mode to retrieve the matrix for.
            create_if_missing: If True, create an empty matrix if it doesn't exist.

        Returns:
            The matrix for the specified mode, or None if it doesn't exist and create_if_missing is False.
        """
        if mode not in self._mats and create_if_missing:
            self._mats[mode] = MatrixODT(
                rows=self._rows,
                cols=self._cols,
                timestamps=self._timestamps,
                init=0.0,
                mode=mode,
            )
        return self._mats.get(mode, None)

    def get_all_od(self) -> Generator[tuple[str, Hashable, Hashable, Timestamp, float], None]:
        for mode, mat in self._mats.items():
            for o, d, t, v in mat.get_all_od():
                yield (mode, o, d, t, v)

    @property
    def shape(self) -> tuple[int, int, int, int] | None:
        """Number of modes followed by the shape of a single matrix."""
        matrix = next(iter(self._mats.values()))
        if matrix is None:
            return None
        else:
            return (len(self._mats),) + matrix.shape  # type: ignore

    def __str__(self):
        """Return a summary with the shape and the loaded modes."""
        shape = self.shape
        if shape is None:
            return "MatrixODT(empty)"
        n_modes = shape[0]
        shape0 = shape[1:]
        list_modes_str = ", ".join(list(self._mats.keys()))
        shape0_str = "x".join(map(str, shape0)) if shape0 is not None else "?"
        return f"MatrixODT({n_modes}x{shape0_str}) [{list_modes_str}]"
