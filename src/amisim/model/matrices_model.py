"""Origin-destination demand matrices, one per mode plus the equivalent one."""

from __future__ import annotations

from matrix import LabelsInput, Timestamp

from ..base.base_loader import InputParameters, InputType
from ..base.base_model import BaseModel
from ..loaders.matrix_loader import MatrixLoader
from .modes_model import ModesModel
from .multi_modal_dynamic_matrix import MatricesType, MatrixODT, MultiModalDynamicMatrix, TimestampsType
from .slice import Slice

__all__ = [
    "MatricesModel",
    "MultiModalDynamicMatrix",
    "MatrixODT",
    "TimestampsType",
    "LabelsInput",
    "Timestamp",
    "MatricesType",
]


class MatricesModel(BaseModel):
    """Hold the demand matrices of each mode and their equivalent sum."""

    def __init__(self):
        """Create an empty matrices collection."""
        super().__init__()
        self._mat: MultiModalDynamicMatrix

    @property
    def matrix(self) -> MultiModalDynamicMatrix:
        """Matrices.

        Returns:
            A dictionary mapping each mode to its demand matrix.

        """
        return self._mat

    def has_mode(self, mode: str) -> bool:
        """Check if the given mode exists in the matrices."""
        return self._mat.has_mode(mode)

    @property
    def modes(self) -> list[str]:
        """Modes.

        Returns:
            The modes and their equivalence factors.

        """
        return self._mat.modes

    def matrix_eq(self, modes: ModesModel) -> MatrixODT:
        """Compute the equivalent matrix based on the provided modes.

        Returns:
            The equivalent matrix obtained summing the modal matrices weighted
            by their `eq_factor`.

        Raises:
            ValueError: If the equivalent matrix has not been computed yet.

        """
        return self._mat._calc_matrix_eq(modes)

    def drop_modes(self, modes: list[str]) -> None:
        self._mat.drop_modes(modes)

    @classmethod
    def read(
        cls,
        centroids: LabelsInput,
        timestamps: TimestampsType,
        kws_matrices: list[dict[str, InputType]],
        slice: Slice | None = None,
        replace_timestamps: bool = False,
        modes: set[str] | None = None,
    ) -> MatricesModel:
        """Read.

        Args:
            # engine: Engine used to read the matrices.
            # modes: Modes providing the equivalence factors.
            centroids: Labels of the matrix rows and columns.
            timestamps: Time slices of the matrices.
            kws_matrices: One entry per mode with its `mode` and `matrices`
                parameters.

        Returns:
            The matrices of every mode plus the equivalent matrix.

        Raises:
            ValueError: If an entry does not specify the mode.

        """
        this = cls()
        if not bool(kws_matrices):
            this.log.warning("No matrices source provided.")
            return this
        # loader._modes = modes.modes
        for kw_matrix in kws_matrices:
            mode = kw_matrix.get("mode")
            if mode is None:
                raise ValueError("Mode must be specified in kws_matrices.")
            mode = str(mode)
            if modes is not None and mode not in modes:
                continue
            if cls.static_log:
                cls.static_log.debug(f"Reading matrix for mode '{mode}'")
            this._read_single_mode(
                kw_matrix=kw_matrix.get("matrices", {}),
                centroids=centroids,
                timestamps=timestamps,
                mode=mode,
                slice=slice,
                replace_timestamps=replace_timestamps,
            )
        # loader._matrix_eq = loader._calc_matrix_eq()
        return this

    def _read_single_mode(
        self,
        kw_matrix: InputType,
        centroids: LabelsInput,
        timestamps: TimestampsType,
        mode: str = "c",
        slice: Slice | None = None,
        replace_timestamps: bool = True,
    ) -> MatricesModel:
        # Internal helper: read.
        """Internal helper: read."""
        if slice is not None and slice.time_slice >= self.app.ini.ASSIGNMENT.MAX_TIMESLICE:
            raise ValueError(f"Time slice must be less than {self.app.ini.ASSIGNMENT.MAX_TIMESLICE} minutes (1 day).")
        additional_filter = None
        timestamp_to_replace = None
        if replace_timestamps or slice is not None:
            additional_filter, new_timestamp_to_replace = self._filter(slice)
            if replace_timestamps and new_timestamp_to_replace is not None:
                timestamp_to_replace = new_timestamp_to_replace
                timestamps = sorted(timestamp_to_replace.values())
        if isinstance(kw_matrix, list):
            ret = MatrixODT(rows=centroids, cols=centroids, timestamps=timestamps, init=0.0)
            for item in kw_matrix:
                if isinstance(item, dict) and "scalar" in item:
                    scalar = item["scalar"]
                    operation = item.get("operation", "+")
                    if operation == "+":
                        ret = ret + scalar
                    elif operation == "-":
                        ret = ret - scalar
                    elif operation == "/":
                        ret = ret / scalar
                    elif operation == "*":
                        ret = ret * scalar
                    else:
                        raise ValueError(f"Unsupported operation: {operation}")
                else:
                    bm = MatrixLoader.read(self.engine, params=item, additional_filters=additional_filter)
                    if bm is None or bm.df is None:
                        raise ValueError("Failed to read matrix from item.")
                    if replace_timestamps and timestamp_to_replace is not None:
                        bm.df["timestamp"] = bm.df["timestamp"].map(timestamp_to_replace)

                    od = MatrixODT.read_df(rows=centroids, cols=centroids, timestamps=timestamps, df=bm.df)

                    operation = "+"
                    if isinstance(item, dict) and "operation" in item:
                        operation = item.get("operation", "+")
                    elif isinstance(item, InputParameters):
                        operation = item.operation or "+"
                    if operation == "+":
                        ret = ret + od
                    elif operation == "-":
                        ret = ret - od
                    elif operation == "/":
                        ret = ret / od
                    elif operation == "*":
                        ret = ret * od
                    else:
                        raise ValueError(f"Unsupported operation: {operation}")
        else:
            bm = MatrixLoader.read(self.engine, params=kw_matrix, additional_filters=additional_filter)
            if bm is None or bm.df is None:
                raise ValueError("Failed to read matrix from item.")
            if replace_timestamps and timestamp_to_replace is not None:
                bm.df["timestamp"] = bm.df["timestamp"].map(timestamp_to_replace)
            ret = MatrixODT.read_df(rows=centroids, cols=centroids, timestamps=timestamps, df=bm.df)
        if not hasattr(self, "_mat") or self._mat is None:
            self._mat = MultiModalDynamicMatrix(rows=ret.rows, cols=ret.cols, timestamps=ret.timestamps, init=0.0)
        self._mat.set_by_mode(mode, ret)
        return self

    def _filter(self, slice: Slice | None) -> tuple[list[str] | None, dict | None]:
        if slice:
            timestamp_to_replace = slice.timestamp_to_id
            additional_filter = []
            for interval in slice.simulation_interval.get_day_intervals():
                start = interval.start.minutes_from_midnight()
                end = interval.end.minutes_from_midnight()
                assert start <= end, "Start time must be less than or equal to end time"
                day_type = interval.simulation_date.day_type
                self.log.debug(f"Processing interval: start={start}, end={end}, day_type={day_type}")
                additional_filter.append(
                    f"((timestamp >= {start} AND timestamp <= {end}) and (day_type = '{day_type}' or day_type = 'all'))"
                )

            additional_filter = [" OR ".join(additional_filter)]
        else:
            additional_filter = None
            timestamp_to_replace = None

        return additional_filter, timestamp_to_replace

    @property
    def shape(self) -> tuple[int, int, int, int] | None:
        """Number of modes followed by the shape of a single matrix."""
        if self._mat is None:
            return None
        return self._mat.shape

    def __str__(self):
        """Return a summary with the shape and the loaded modes."""
        shape = self.shape
        if shape is None:
            return "Matrix(empty)"
        n_modes = shape[0]
        shape0 = shape[1:]
        list_modes_str = ", ".join(self._mat.modes)
        shape0_str = "x".join(map(str, shape0)) if shape0 is not None else "?"
        return f"Matrix({n_modes}x{shape0_str}) [{list_modes_str}]"
