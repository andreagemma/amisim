"""Time-indexed origin-destination matrices."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from os import PathLike
from typing import Any, TypeAlias, cast

import pandas as pd

from .matrix_od import LabelMap, LabelsInput, MatrixInit, MatrixOD, convert_to_dict

Timestamp: TypeAlias = int
ODTInit: TypeAlias = Mapping[Timestamp, MatrixInit] | MatrixInit


class MatrixODT:
    """A collection of ``MatrixOD`` instances indexed by timestamp labels.

    Missing timestamps are treated as zero matrices when reading values. Assigning
    a timestamp creates or replaces the corresponding ``MatrixOD``.
    """

    def __init__(
        self,
        rows: LabelsInput,
        cols: LabelsInput,
        timestamps: list[Timestamp] | set[Timestamp] | tuple[Timestamp, ...] | None = None,
        init: ODTInit | MatrixODT | None = None,
        copy: bool = False,
        mode: str | None = None,
    ) -> None:
        """Create a time-indexed collection of origin-destination matrices.

        Args:
            rows: Row labels or a label-to-position mapping.
            cols: Column labels or a label-to-position mapping.
            timestamps: Timestamp labels represented by the collection.
            init: Initial scalar, matrix mapping, ``MatrixOD``, or ``MatrixODT``.
            copy: Whether to copy matrix data from the initializer.
            mode: Optional metadata associated with the matrices.
        """
        self.rows: LabelMap
        self.cols: LabelMap
        self.timestamps: set[Timestamp]
        self.mode: str | None
        self.ods: dict[Timestamp, MatrixOD]

        if isinstance(init, MatrixODT):
            self.rows = init.rows
            self.cols = init.cols
            self.timestamps = set(init.timestamps)
            self.mode = init.mode if mode is None else mode
            self.ods = {
                timestamp: matrix.copy(copy_data=True) if copy else matrix for timestamp, matrix in init.ods.items()
            }
            return
        if isinstance(init, MatrixOD):
            self.rows = init.rows
            self.cols = init.cols
            if timestamps is None:
                raise ValueError("Timestamps must be provided when initializing with a MatrixOD.")
            self.timestamps = set(timestamps)
            self.mode = init.mode if mode is None else mode
            self.ods = {timestamp: self._coerce_matrix(init, copy=True) for timestamp in timestamps}
            return
        self.rows = convert_to_dict(rows)
        self.cols = convert_to_dict(cols)
        if timestamps is None:
            raise ValueError("Timestamps must be provided when initializing without a MatrixODT.")
        self.timestamps = set(timestamps)
        self.mode = mode
        self.ods = {timestamp: MatrixOD(self.rows, self.cols, mode=mode) for timestamp in self.timestamps}

        if init is not None:
            if isinstance(init, (int, float)):
                init = {timestamp: init for timestamp in self.timestamps}
            elif not isinstance(init, dict):
                raise TypeError("Initialization value must be a number or a dictionary mapping timestamps to values.")
            for timestamp, value in init.items():
                timestamp = cast(Timestamp, timestamp)
                self.timestamps.add(timestamp)
                self.ods[timestamp] = self._coerce_matrix(cast(MatrixInit, value), copy=copy)

    def _coerce_matrix(
        self,
        value: MatrixInit,
        *,
        copy: bool,
    ) -> MatrixOD:
        """Internal helper: coerce matrix."""
        if isinstance(value, MatrixOD):
            if value.rows != self.rows or value.cols != self.cols:
                raise ValueError("Matrices must have the same row and column labels.")
            return value.copy(copy_data=True) if copy else value
        return MatrixOD(self.rows, self.cols, init=value, copy=copy, mode=self.mode)

    def _zero_matrix(self) -> MatrixOD:
        """Internal helper: zero matrix."""
        return MatrixOD(self.rows, self.cols, mode=self.mode)

    def _matrix_or_zero(self, timestamp: Timestamp) -> MatrixOD:
        """Internal helper: matrix or zero."""
        matrix = self.ods.get(timestamp)
        return matrix if matrix is not None else self._zero_matrix()

    def _ensure_same_axes(self, other: MatrixODT) -> None:
        """Internal helper: ensure same axes."""
        if self.rows != other.rows or self.cols != other.cols:
            raise ValueError("Matrices must have the same row and column labels.")

    def copy(self, copy_data: bool = True) -> MatrixODT:
        """Return a copy of this time-indexed matrix.

        Args:
            copy_data: Whether to copy the underlying matrices or share them.

        Returns:
            A time-indexed matrix with the same labels, values, and metadata.
        """
        return MatrixODT(
            self.rows,
            self.cols,
            self.timestamps,
            init=self,
            copy=copy_data,
            mode=self.mode,
        )

    def get_matrix_at_t(self, timestamp: Timestamp) -> MatrixOD:
        """Return the matrix at ``timestamp``, or a zero matrix if it is missing."""
        return self._matrix_or_zero(timestamp)

    def get_od(self, timestamp: Timestamp, origin: Hashable, destination: Hashable) -> float:
        """Return one origin-destination value, using zero for a missing timestamp."""
        if timestamp not in self.ods:
            return 0.0
        return float(self.ods[timestamp][origin, destination])

    def __getitem__(
        self,
        pos: Timestamp | tuple[Hashable, Hashable, Timestamp],
    ) -> MatrixOD | float:
        """Return a timestamp matrix or one origin-destination value.

        Args:
            pos: Timestamp or origin, destination, and timestamp tuple.

        Returns:
            The selected matrix or scalar value.
        """
        if not isinstance(pos, tuple):
            return self._matrix_or_zero(pos)
        if len(pos) != 3:
            raise TypeError("Use matrix[o, d, timestamp] for scalar access.")
        origin, destination, timestamp = pos
        if timestamp not in self.ods:
            return 0.0
        return self.ods[timestamp][origin, destination]

    def __setitem__(
        self,
        pos: Timestamp | tuple[Hashable, Hashable, Timestamp],
        value: MatrixOD | MatrixInit | int | float,
    ) -> None:
        """Assign a timestamp matrix or one origin-destination value.

        Args:
            pos: Timestamp or origin, destination, and timestamp tuple.
            value: Matrix, scalar, or matrix initializer to assign.
        """
        if not isinstance(pos, tuple):
            self.timestamps.add(pos)
            self.ods[pos] = self._coerce_matrix(value, copy=False)
            return
        if len(pos) != 3:
            raise TypeError("Use matrix[o, d, timestamp] for scalar access.")
        origin, destination, timestamp = pos
        if timestamp not in self.ods:
            self.timestamps.add(timestamp)
            self.ods[timestamp] = self._zero_matrix()
        if not isinstance(value, (int, float)):
            raise TypeError("Scalar assignment requires an int or float value.")
        self.ods[timestamp][origin, destination] = value

    def sum(self, axis: int | None = None) -> float | MatrixOD | MatrixODT:
        """Sum all values or collapse one axis.

        ``axis=None`` returns a scalar. ``axis=0`` and ``axis=1`` preserve the
        timestamp dimension. ``axis=2`` sums all timestamps into one ``MatrixOD``.

        Args:
            axis: Axis to collapse, or ``None`` to sum all values.

        Returns:
            A scalar or matrix with the requested aggregation.
        """
        if axis is None:
            return sum(matrix.sum() for matrix in self.ods.values())
        if axis == 0:
            summed_cols = MatrixODT(["sum"], self.cols, self.timestamps, mode=self.mode)
            for timestamp, matrix in self.ods.items():
                summed_cols[timestamp] = matrix.sum(axis=0)
            return summed_cols
        if axis == 1:
            summed_rows = MatrixODT(self.rows, ["sum"], self.timestamps, mode=self.mode)
            for timestamp, matrix in self.ods.items():
                summed_rows[timestamp] = matrix.sum(axis=1)
            return summed_rows
        if axis == 2:
            summed_timestamps = MatrixOD(self.rows, self.cols, mode=self.mode)
            for matrix in self.ods.values():
                summed_timestamps += matrix
            return summed_timestamps
        raise ValueError("Axis must be 0, 1, 2, or None.")

    def __add__(self, other: int | float | MatrixODT) -> MatrixODT:
        """Add a scalar or an axis-compatible time-indexed matrix.

        Args:
            other: Scalar or time-indexed matrix to add.

        Returns:
            A new time-indexed matrix containing the sum.
        """
        result = self.copy()
        result += other
        return result

    def __iadd__(self, other: int | float | MatrixODT) -> MatrixODT:
        """Add a scalar or axis-compatible matrix in place.

        Args:
            other: Scalar or time-indexed matrix to add.

        Returns:
            This matrix after the update.
        """
        if isinstance(other, MatrixODT):
            self._ensure_same_axes(other)
            timestamps = self.timestamps | other.timestamps
            self.ods = {
                timestamp: self._matrix_or_zero(timestamp) + other._matrix_or_zero(timestamp)
                for timestamp in timestamps
            }
            self.timestamps = timestamps
        elif isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            for matrix in self.ods.values():
                matrix += other
        else:
            raise TypeError("Unsupported operand type for addition.")
        return self

    def __sub__(self, other: int | float | MatrixODT) -> MatrixODT:
        """Subtract a scalar or an axis-compatible time-indexed matrix.

        Args:
            other: Scalar or time-indexed matrix to subtract.

        Returns:
            A new time-indexed matrix containing the difference.
        """
        result = self.copy()
        result -= other
        return result

    def __isub__(self, other: int | float | MatrixODT) -> MatrixODT:
        """Subtract a scalar or axis-compatible matrix in place.

        Args:
            other: Scalar or time-indexed matrix to subtract.

        Returns:
            This matrix after the update.
        """
        if isinstance(other, MatrixODT):
            self._ensure_same_axes(other)
            timestamps = self.timestamps | other.timestamps
            self.ods = {
                timestamp: self._matrix_or_zero(timestamp) - other._matrix_or_zero(timestamp)
                for timestamp in timestamps
            }
            self.timestamps = timestamps
        elif isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            for matrix in self.ods.values():
                matrix -= other
        else:
            raise TypeError("Unsupported operand type for subtraction.")
        return self

    def __mul__(self, other: int | float | MatrixODT) -> MatrixODT:
        """Multiply by a scalar or axis-compatible matrix element-wise.

        Args:
            other: Scalar or time-indexed matrix multiplier.

        Returns:
            A new time-indexed matrix containing the product.
        """
        result = self.copy()
        result *= other
        return result

    def __imul__(self, other: int | float | MatrixODT) -> MatrixODT:
        """Multiply by a scalar or axis-compatible matrix in place.

        Args:
            other: Scalar or time-indexed matrix multiplier.

        Returns:
            This matrix after the update.
        """
        if isinstance(other, MatrixODT):
            self._ensure_same_axes(other)
            timestamps = self.timestamps | other.timestamps
            self.ods = {
                timestamp: self._matrix_or_zero(timestamp) * other._matrix_or_zero(timestamp)
                for timestamp in timestamps
            }
            self.timestamps = timestamps
        elif isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            for matrix in self.ods.values():
                matrix *= other
        else:
            raise TypeError("Unsupported operand type for multiplication.")
        return self

    def __truediv__(self, other: int | float | MatrixODT) -> MatrixODT:
        """Divide by a scalar or axis-compatible matrix element-wise.

        Args:
            other: Scalar or time-indexed matrix divisor.

        Returns:
            A new time-indexed matrix containing the quotient.
        """
        result = self.copy()
        result /= other
        return result

    def __itruediv__(self, other: int | float | MatrixODT) -> MatrixODT:
        """Divide by a scalar or axis-compatible matrix in place.

        Args:
            other: Scalar or time-indexed matrix divisor.

        Returns:
            This matrix after the update.
        """
        if isinstance(other, MatrixODT):
            self._ensure_same_axes(other)
            timestamps = self.timestamps | other.timestamps
            self.ods = {
                timestamp: self._matrix_or_zero(timestamp) / other._matrix_or_zero(timestamp)
                for timestamp in timestamps
            }
            self.timestamps = timestamps
        elif isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            for matrix in self.ods.values():
                matrix /= other
        else:
            raise TypeError("Unsupported operand type for division.")
        return self

    def nan_to_num(
        self,
        copy: bool = True,
        nan: float = 0.0,
        posinf: float | None = None,
        neginf: float | None = None,
    ) -> None:
        """Replace NaN and infinite values in every timestamp matrix.

        Args:
            copy: Whether to return new arrays instead of updating in place.
            nan: Replacement value for NaN entries.
            posinf: Replacement value for positive infinity entries.
            neginf: Replacement value for negative infinity entries.
        """
        for matrix in self.ods.values():
            matrix.nan_to_num(copy=copy, nan=nan, posinf=posinf, neginf=neginf)

    @staticmethod
    def read_df(
        rows: LabelsInput,
        cols: LabelsInput,
        timestamps: (list[Timestamp] | set[Timestamp] | tuple[Timestamp, ...] | None) = None,
        df: pd.DataFrame | None = None,
        o_field: str = "o",
        d_field: str = "d",
        timestamp_field: str = "timestamp",
        value_field: str = "value",
    ) -> MatrixODT:
        """Create a time-indexed matrix from a long-form DataFrame.

        For backwards compatibility, the third positional argument may be the
        DataFrame itself. When ``timestamps`` is omitted, it is inferred from the
        DataFrame in first-seen order.

        Args:
            rows: Row labels or a label-to-position mapping.
            cols: Column labels or a label-to-position mapping.
            timestamps: Optional timestamp labels.
            df: DataFrame containing origin, destination, timestamp, and value columns.
            o_field: Name of the origin column.
            d_field: Name of the destination column.
            timestamp_field: Name of the timestamp column.
            value_field: Name of the value column.

        Returns:
            A time-indexed matrix populated from ``df``.
        """
        if df is None and isinstance(timestamps, pd.DataFrame):
            df = timestamps
            timestamps = None
        if df is None:
            raise TypeError("df is required.")

        frame = df[[o_field, d_field, timestamp_field, value_field]].rename(  # pyright: ignore
            columns={
                o_field: "o",
                d_field: "d",
                timestamp_field: "timestamp",
                value_field: "value",
            }
        )
        if timestamps is None:
            timestamps = list(pd.unique(frame["timestamp"]))  # pyright: ignore

        ods: dict[Timestamp, MatrixOD] = {}
        for timestamp, group in frame.groupby("timestamp", sort=False):  # pyright: ignore
            ods[cast(Timestamp, timestamp)] = MatrixOD.read_df(
                rows=rows,
                cols=cols,
                df=group,  # pyright: ignore
                o_field="o",
                d_field="d",
                value_field="value",
            )
        return MatrixODT(rows, cols, timestamps=timestamps, init=ods)

    @staticmethod
    def read_csv(
        rows: LabelsInput,
        cols: LabelsInput,
        file: str | PathLike[str],
        timestamps: list[Timestamp] | set[Timestamp] | tuple[Timestamp, ...] | None = None,
        o_field: str = "o",
        d_field: str = "d",
        timestamp_field: str = "timestamp",
        value_field: str = "value",
    ) -> MatrixODT:
        """Create a time-indexed matrix from a long-form CSV file.

        Args:
            rows: Row labels or a label-to-position mapping.
            cols: Column labels or a label-to-position mapping.
            file: CSV path or path-like object.
            timestamps: Optional timestamp labels.
            o_field: Name of the origin column.
            d_field: Name of the destination column.
            timestamp_field: Name of the timestamp column.
            value_field: Name of the value column.

        Returns:
            A time-indexed matrix populated from the CSV file.
        """
        df = pd.read_csv(file, usecols=[o_field, d_field, value_field, timestamp_field])
        return MatrixODT.read_df(
            rows=rows,
            cols=cols,
            timestamps=timestamps,
            df=df,
            o_field=o_field,
            d_field=d_field,
            timestamp_field=timestamp_field,
            value_field=value_field,
        )

    def write_df(
        self,
        o_field: str = "o",
        d_field: str = "d",
        timestamp_field: str = "timestamp",
        value_field: str = "value",
    ) -> pd.DataFrame:
        """Return the data as a sorted long-form DataFrame.

        Args:
            o_field: Name of the origin column in the result.
            d_field: Name of the destination column in the result.
            timestamp_field: Name of the timestamp column in the result.
            value_field: Name of the value column in the result.

        Returns:
            A sorted DataFrame with one row per matrix cell and timestamp.
        """
        data: list[dict[str, Any]] = []
        for timestamp, od_matrix in self.ods.items():
            for origin, origin_index in od_matrix.rows.items():
                for destination, destination_index in od_matrix.cols.items():
                    data.append(
                        {
                            timestamp_field: timestamp,
                            o_field: origin,
                            d_field: destination,
                            value_field: od_matrix.mat[origin_index, destination_index],
                        }
                    )
        return pd.DataFrame(data).sort_values([timestamp_field, o_field, d_field])

    def write_csv(
        self,
        file: str | PathLike[str],
        o_field: str = "o",
        d_field: str = "d",
        timestamp_field: str = "timestamp",
        value_field: str = "value",
    ) -> None:
        """Write the data as a sorted long-form CSV file.

        Args:
            file: CSV path or path-like object.
            o_field: Name of the origin column.
            d_field: Name of the destination column.
            timestamp_field: Name of the timestamp column.
            value_field: Name of the value column.
        """
        df = self.write_df(
            o_field=o_field,
            d_field=d_field,
            timestamp_field=timestamp_field,
            value_field=value_field,
        )
        df.to_csv(file, index=False)

    @property
    def shape(self) -> tuple[int, int, int] | None:
        """Return the shape of the matrix as (n_timestamps, n_origins, n_destinations)."""
        if not self.ods:
            return None
        n_timestamps = len(self.ods)
        first_od_matrix = next(iter(self.ods.values()))
        n_origins = len(first_od_matrix.rows)
        n_destinations = len(first_od_matrix.cols)
        return (n_timestamps, n_origins, n_destinations)
