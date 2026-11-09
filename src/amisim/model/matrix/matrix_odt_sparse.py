"""Time-indexed origin-destination matrices."""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Generator, Hashable, Iterable, Mapping
from itertools import product
from os import PathLike
from typing import TypeAlias

import numpy as np
import pandas as pd

from .matrix_od import LabelMap, LabelsInput, convert_to_dict
from .matrix_odt import Timestamp

Coordinate: TypeAlias = tuple[Hashable, Hashable, Timestamp]
SparseValues: TypeAlias = Mapping[Coordinate, float]


def _add(left: float, right: float) -> float:
    """Add two scalar values."""
    return left + right


def _subtract(left: float, right: float) -> float:
    """Subtract two scalar values."""
    return left - right


def _multiply(left: float, right: float) -> float:
    """Multiply two scalar values."""
    return left * right


def _divide(left: float, right: float) -> float:
    """Divide two scalar values using NumPy's IEEE zero-division behavior."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(np.divide(left, right))


class MatrixODTSparse:
    """A sparse time-indexed collection of origin-destination values.

    Unstored coordinates have a value of zero. Assigning a nonzero coordinate
    creates it; assigning zero removes it from sparse storage.
    """

    def __init__(
        self,
        rows: LabelsInput,
        cols: LabelsInput,
        timestamps: list[Timestamp] | set[Timestamp] | tuple[Timestamp, ...] | None = None,
        init: int | float | MatrixODTSparse | SparseValues | None = None,
        copy: bool = False,
        mode: str | None = None,
    ) -> None:
        """Create a time-indexed collection of origin-destination matrices.

        Args:
            rows: Row labels or a label-to-position mapping.
            cols: Column labels or a label-to-position mapping.
            timestamps: Timestamp labels represented by the collection.
            init: Scalar value, coordinate-to-value mapping, or another sparse matrix.
            copy: Whether to copy sparse values when ``init`` is another sparse matrix.
            mode: Optional metadata associated with the matrices.
        """
        self.rows: LabelMap
        self.cols: LabelMap
        self.timestamps: set[Timestamp]
        self.mode: str | None
        self.ods: dict[tuple[Hashable, Hashable, Timestamp], float]

        if isinstance(init, MatrixODTSparse):
            self.rows = init.rows
            self.cols = init.cols
            self.timestamps = set(init.timestamps)
            self.mode = init.mode if mode is None else mode
            self.ods = init.ods.copy() if copy else init.ods
            return
        self.rows = convert_to_dict(rows)
        self.cols = convert_to_dict(cols)
        if timestamps is None:
            raise ValueError("Timestamps must be provided when initializing without a sparse matrix.")
        self.timestamps = set(timestamps)
        self.mode = mode
        self.ods = {}

        if init is not None:
            if isinstance(init, (int, float)):
                for t, o, d in product(self.timestamps, self.rows, self.cols):
                    self._set_value((o, d, t), float(init))
                return
            if isinstance(init, Mapping):
                for key, value in init.items():
                    self._set_value(key, float(value))
                return
            else:
                raise TypeError("Initialization value must be a number or a coordinate mapping.")

    def _validate_coordinate(self, key: Coordinate) -> None:
        """Validate one sparse coordinate against the matrix axes."""
        origin, destination, _ = key
        if origin not in self.rows:
            raise KeyError(f"Row label {origin!r} not found.")
        if destination not in self.cols:
            raise KeyError(f"Column label {destination!r} not found.")

    def _set_value(self, key: Coordinate, value: float) -> None:
        """Store nonzero values and remove explicit zeros."""
        self._validate_coordinate(key)
        self.timestamps.add(key[2])
        if value == 0.0:
            self.ods.pop(key, None)
        else:
            self.ods[key] = value

    def _ensure_same_axes(self, other: MatrixODTSparse) -> None:
        """Raise when two sparse matrices have different labels."""
        if self.rows != other.rows or self.cols != other.cols:
            raise ValueError("Matrices must have the same row and column labels.")

    def _apply_binary(
        self,
        other: int | float | SparseValues | MatrixODTSparse,
        operation: Callable[[float, float], float],
        *,
        division: bool = False,
    ) -> None:
        """Apply an element-wise operation in place."""
        if isinstance(other, MatrixODTSparse):
            self._ensure_same_axes(other)
            right_values = other.ods.copy()
            timestamps = self.timestamps | other.timestamps
        elif isinstance(other, Mapping):
            right_values = dict(other)
            for key in right_values:
                self._validate_coordinate(key)
            timestamps = self.timestamps | {key[2] for key in right_values}
        elif isinstance(other, (int, float)):
            if other == 0 and operation in (_add, _subtract):
                return
            if division and other == 0:
                for timestamp, origin, destination in product(self.timestamps, self.rows, self.cols):
                    key = (origin, destination, timestamp)
                    self._set_value(key, operation(self.ods.get(key, 0.0), float(other)))
            elif operation is _multiply and other == 0:
                self.ods.clear()
            elif operation is _add or operation is _subtract:
                for timestamp, origin, destination in product(self.timestamps, self.rows, self.cols):
                    key = (origin, destination, timestamp)
                    self._set_value(key, operation(self.ods.get(key, 0.0), float(other)))
            else:
                for key, value in tuple(self.ods.items()):
                    self._set_value(key, operation(value, float(other)))
            return
        else:
            raise TypeError("Unsupported operand type.")

        self.timestamps = timestamps
        keys: Iterable[Coordinate]
        if division:
            keys = (
                (origin, destination, timestamp)
                for timestamp, origin, destination in product(timestamps, self.rows, self.cols)
            )
        else:
            keys = self.ods.keys() | right_values.keys()
        results = {key: operation(self.ods.get(key, 0.0), right_values.get(key, 0.0)) for key in keys}
        for key, value in results.items():
            self._set_value(key, value)

    def copy(self, copy_data: bool = True) -> MatrixODTSparse:
        """Return a copy of this time-indexed matrix.

        Args:
            copy_data: Whether to copy sparse values or share their mapping.

        Returns:
            A time-indexed matrix with the same labels, values, and metadata.
        """
        return MatrixODTSparse(
            rows=self.rows,
            cols=self.cols,
            timestamps=self.timestamps,
            init=self,
            copy=copy_data,
            mode=self.mode,
        )

    def get_od(self, origin: Hashable, destination: Hashable, timestamp: Timestamp) -> float:
        """Return one value, treating an unstored coordinate as zero."""
        self._validate_coordinate((origin, destination, timestamp))
        return self.ods.get((origin, destination, timestamp), 0.0)

    def get_all_od(self) -> Generator[tuple[Hashable, Hashable, Timestamp, float], None, None]:
        """Yield each explicitly stored origin, destination, timestamp, and value."""
        for (o, d, t), v in self.ods.items():
            yield o, d, t, v

    def __getitem__(
        self,
        pos: Timestamp | tuple[Hashable, Hashable, Timestamp],
    ) -> MatrixODTSparse | float:
        """Return a timestamp matrix or one origin-destination value.

        Args:
            pos: Timestamp or origin, destination, and timestamp tuple.

        Returns:
            The selected matrix or scalar value.
        """
        if not isinstance(pos, tuple):
            if not isinstance(pos, int):
                raise TypeError("Timestamp access requires an integer timestamp.")
            return MatrixODTSparse(
                rows=self.rows,
                cols=self.cols,
                timestamps={pos},
                init={(o, d, pos): value for (o, d, t), value in self.ods.items() if t == pos},
                copy=False,
                mode=self.mode,
            )
        if len(pos) != 3:
            raise TypeError("Use matrix[o, d, timestamp] for scalar access.")
        origin, destination, timestamp = pos
        return self.get_od(origin, destination, timestamp)

    def __setitem__(
        self,
        pos: tuple[Hashable, Hashable, Timestamp],
        value: int | float,
    ) -> None:
        """Assign a timestamp matrix or one origin-destination value.

        Args:
            pos: Origin, destination, and timestamp tuple.
            value: Scalar value to assign.
        """
        if len(pos) != 3:
            raise TypeError("Use matrix[o, d, timestamp] for scalar access.")
        origin, destination, timestamp = pos
        key = (origin, destination, timestamp)
        self._set_value(key, float(value))

    def sum(self) -> float:
        """Sum all values in the matrix.

        Returns:
            The sum of all values as a scalar.
        """
        return sum(self.ods.values())

    def __add__(self, other: int | float | SparseValues | MatrixODTSparse) -> MatrixODTSparse:
        """Add a scalar or an axis-compatible time-indexed matrix.

        Args:
            other: Scalar or time-indexed matrix to add.

        Returns:
            A new time-indexed matrix containing the sum.
        """
        result = self.copy()
        result += other
        return result

    def __iadd__(self, other: int | float | SparseValues | MatrixODTSparse) -> MatrixODTSparse:
        """Add a scalar or axis-compatible matrix in place.

        Args:
            other: Scalar or time-indexed matrix to add.

        Returns:
            This matrix after the update.
        """
        self._apply_binary(other, _add)
        return self

    def __sub__(self, other: int | float | SparseValues | MatrixODTSparse) -> MatrixODTSparse:
        """Subtract a scalar or an axis-compatible time-indexed matrix.

        Args:
            other: Scalar or time-indexed matrix to subtract.

        Returns:
            A new time-indexed matrix containing the difference.
        """
        result = self.copy()
        result -= other
        return result

    def __isub__(self, other: int | float | SparseValues | MatrixODTSparse) -> MatrixODTSparse:
        """Subtract a scalar or axis-compatible matrix in place.

        Args:
            other: Scalar or time-indexed matrix to subtract.

        Returns:
            This matrix after the update.
        """
        self._apply_binary(other, _subtract)
        return self

    def __mul__(self, other: int | float | SparseValues | MatrixODTSparse) -> MatrixODTSparse:
        """Multiply by a scalar or axis-compatible matrix element-wise.

        Args:
            other: Scalar or time-indexed matrix multiplier.

        Returns:
            A new time-indexed matrix containing the product.
        """
        result = self.copy()
        result *= other
        return result

    __radd__ = __add__

    def __rsub__(self, other: int | float) -> MatrixODTSparse:
        """Subtract this sparse matrix from a scalar."""
        if not isinstance(other, (int, float)):
            return NotImplemented
        result = self.copy()
        for timestamp, origin, destination in product(result.timestamps, result.rows, result.cols):
            key = (origin, destination, timestamp)
            result._set_value(key, _subtract(float(other), result.ods.get(key, 0.0)))
        return result

    __rmul__ = __mul__

    def __imul__(self, other: int | float | SparseValues | MatrixODTSparse) -> MatrixODTSparse:
        """Multiply by a scalar or axis-compatible matrix in place.

        Args:
            other: Scalar or time-indexed matrix multiplier.

        Returns:
            This matrix after the update.
        """
        self._apply_binary(other, _multiply)
        return self

    def __truediv__(self, other: int | float | SparseValues | MatrixODTSparse) -> MatrixODTSparse:
        """Divide by a scalar or axis-compatible matrix element-wise.

        Args:
            other: Scalar or time-indexed matrix divisor.

        Returns:
            A new time-indexed matrix containing the quotient.
        """
        result = self.copy()
        result /= other
        return result

    def __rtruediv__(self, other: int | float) -> MatrixODTSparse:
        """Divide a scalar by this sparse matrix using IEEE zero behavior."""
        if not isinstance(other, (int, float)):
            return NotImplemented
        result = self.copy()
        for timestamp, origin, destination in product(result.timestamps, result.rows, result.cols):
            key = (origin, destination, timestamp)
            result._set_value(key, _divide(float(other), result.ods.get(key, 0.0)))
        return result

    def __itruediv__(self, other: int | float | SparseValues | MatrixODTSparse) -> MatrixODTSparse:
        """Divide by a scalar or axis-compatible matrix in place.

        Args:
            other: Scalar or time-indexed matrix divisor.

        Returns:
            This matrix after the update.
        """
        self._apply_binary(other, _divide, division=True)
        return self

    def nan_to_num(
        self,
        copy: bool = True,
        nan: float = 0.0,
        posinf: float | None = None,
        neginf: float | None = None,
    ) -> None:
        """Replace NaN and infinite values in sparse storage.

        Args:
            copy: Whether to replace the sparse value mapping before updating it.
            nan: Replacement value for NaN entries.
            posinf: Replacement for positive infinity; defaults to the largest
                finite float.
            neginf: Replacement for negative infinity; defaults to the smallest
                finite float.
        """
        replacements: dict[Coordinate, float] = {}
        for key, value in self.ods.items():
            if math.isnan(value):
                replacements[key] = nan
            elif math.isinf(value) and value > 0:
                replacements[key] = sys.float_info.max if posinf is None else posinf
            elif math.isinf(value) and value < 0:
                replacements[key] = -sys.float_info.max if neginf is None else neginf
            else:
                replacements[key] = value
        if copy:
            self.ods = {}
            for key, value in replacements.items():
                self._set_value(key, value)
        else:
            for key, value in replacements.items():
                self._set_value(key, value)

    def fill_nan_and_inf(
        self,
        copy: bool = True,
        nan: float = 0.0,
        posinf: float | None = None,
        neginf: float | None = None,
    ) -> None:
        """Replace NaN and infinite values using :meth:`nan_to_num` behavior.

        Args:
            copy: Whether to replace the sparse value mapping before updating it.
            nan: Replacement value for NaN entries.
            posinf: Replacement for positive infinity.
            neginf: Replacement for negative infinity.
        """
        self.nan_to_num(copy=copy, nan=nan, posinf=posinf, neginf=neginf)

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
    ) -> MatrixODTSparse:
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

        init = frame.set_index(["o", "d", "timestamp"])["value"].to_dict()
        return MatrixODTSparse(rows, cols, timestamps=timestamps, init=init)

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
    ) -> MatrixODTSparse:
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
        return MatrixODTSparse.read_df(
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
        reset_index: bool = True,
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
        records = [
            {
                o_field: origin,
                d_field: destination,
                timestamp_field: timestamp,
                value_field: value,
            }
            for (origin, destination, timestamp), value in self.ods.items()
        ]
        df = pd.DataFrame(
            records,
            columns=[o_field, d_field, timestamp_field, value_field],
        )
        if reset_index:
            return df.sort_values([timestamp_field, o_field, d_field]).reset_index(drop=True)
        return df.set_index([o_field, d_field, timestamp_field]).sort_index()

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
        if not self.timestamps:
            return None
        n_timestamps = len(self.timestamps)
        n_origins = len(self.rows)
        n_destinations = len(self.cols)
        return (n_timestamps, n_origins, n_destinations)


__all__ = ["MatrixODTSparse"]
