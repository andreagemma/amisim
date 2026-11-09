"""Two-dimensional origin-destination matrices with row and column labels."""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from os import PathLike
from types import MappingProxyType
from typing import Any, TypeAlias

import numpy as np
import pandas as pd

Label: TypeAlias = Hashable
LabelMap: TypeAlias = Mapping[Label, int]
LabelsInput: TypeAlias = Sequence[Label] | np.ndarray | LabelMap
MatrixInit: TypeAlias = (
    Mapping[Label, Mapping[Label, float]] | Sequence[Sequence[float]] | int | float | np.ndarray | None
)


def convert_to_dict(labels: LabelsInput) -> LabelMap:
    """Convert labels to an immutable label-position mapping.

    Args:
        labels: Sequence, NumPy array, or existing label-position mapping.

    Returns:
        An immutable mapping from each label to its zero-based position.
    """
    if isinstance(labels, Mapping):
        converted_mapping: dict[Label, int] = dict(labels)
        positions = list(converted_mapping.values())
        if not all(isinstance(position, int) for position in positions):  # type: ignore
            raise ValueError("Label mapping values must be integer positions.")
        if sorted(positions) != list(range(len(converted_mapping))):
            raise ValueError("Label mapping positions must be unique and zero-based.")
        return MappingProxyType(converted_mapping)

    if isinstance(labels, np.ndarray):
        labels = labels.tolist()

    if isinstance(labels, (str, bytes)) or not isinstance(labels, Sequence):
        raise TypeError("Labels must be a sequence, NumPy array, or mapping.")

    converted_labels: dict[Label, int] = {}
    for index, label in enumerate(labels):
        if label in converted_labels:
            raise ValueError(f"Duplicate label: {label!r}")
        converted_labels[label] = index
    return MappingProxyType(converted_labels)


class MatrixOD:
    """A NumPy-backed matrix addressed by origin and destination labels.

    Args:
        rows: Row labels or a label-to-position mapping.
        cols: Column labels or a label-to-position mapping.
        init: Optional nested dictionaries, rectangular sequence, scalar value,
            NumPy array, or another ``MatrixOD``.
        copy: Whether to copy NumPy or ``MatrixOD`` data instead of sharing it.
        mode: Optional metadata preserved on copies and arithmetic results.
    """

    def __init__(
        self,
        rows: LabelsInput,
        cols: LabelsInput,
        init: MatrixInit = None,
        copy: bool = False,
        mode: str | None = None,
    ) -> None:
        """Create an origin-destination matrix with labeled axes.

        Args:
            rows: Row labels or a label-to-position mapping.
            cols: Column labels or a label-to-position mapping.
            init: Optional initial matrix data.
            copy: Whether to copy array-backed initial data.
            mode: Optional metadata associated with the matrix.
        """
        self.rows = convert_to_dict(rows)
        self.cols = convert_to_dict(cols)
        self.mode = mode
        self.mat = self._init_array(init, copy=copy)

    def _init_array(
        self,
        init: MatrixInit,
        *,
        copy: bool,
    ) -> np.ndarray:
        """Internal helper: init array."""
        shape = (len(self.rows), len(self.cols))
        if init is None:
            return np.zeros(shape, dtype=float)
        if isinstance(init, MatrixOD):
            array = init.mat.copy() if copy else init.mat
        elif isinstance(init, Mapping):
            array = np.zeros(shape, dtype=float)
            for row_label, row_values in init.items():
                for col_label, value in row_values.items():
                    row_index = self._row_position(row_label)
                    col_index = self._col_position(col_label)
                    array[row_index, col_index] = value
        elif isinstance(init, np.ndarray):
            array = init.copy() if copy else init
        elif isinstance(init, (int, float)):
            array = np.full(shape, init, dtype=float)
        elif isinstance(init, Sequence) and not isinstance(init, (str, bytes)):  # pyright: ignore[reportUnnecessaryIsInstance]
            array = np.asarray(init, dtype=float)
        else:
            raise TypeError("Unsupported type for init.")
        if array.shape != shape:
            raise ValueError(f"Initial data shape {array.shape} does not match matrix shape {shape}.")
        return array

    def _row_position(self, label: Label) -> int:
        """Internal helper: row position."""
        try:
            return self.rows[label]
        except KeyError as exc:
            raise KeyError(f"Row label {label!r} not found.") from exc

    def _col_position(self, label: Label) -> int:
        """Internal helper: col position."""
        try:
            return self.cols[label]
        except KeyError as exc:
            raise KeyError(f"Column label {label!r} not found.") from exc

    def _ensure_same_labels(self, other: MatrixOD) -> None:
        """Internal helper: ensure same labels."""
        if self.rows != other.rows or self.cols != other.cols:
            raise ValueError("Matrices must have the same row and column labels.")

    def copy(self, copy_data: bool = True) -> MatrixOD:
        """Return a copy of this matrix.

        Args:
            copy_data: Whether to copy the underlying array or share it.

        Returns:
            A matrix with the same labels, values, and metadata.
        """
        return MatrixOD(
            self.rows,
            self.cols,
            init=self.mat,
            copy=copy_data,
            mode=self.mode,
        )

    def __getitem__(self, pos: tuple[Label, Label]) -> float:
        """Return the value at an origin and destination pair.

        Args:
            pos: Origin and destination label pair.

        Returns:
            The value at ``pos``.
        """
        row_label, col_label = pos
        return self.mat[self._row_position(row_label), self._col_position(col_label)]

    def __setitem__(self, pos: tuple[Label, Label], value: float) -> None:
        """Set the value at an origin and destination pair.

        Args:
            pos: Origin and destination label pair.
            value: Value assigned to ``pos``.
        """
        row_label, col_label = pos
        self.mat[self._row_position(row_label), self._col_position(col_label)] = value

    def __repr__(self) -> str:
        """Return the NumPy representation of the matrix."""
        return repr(self.mat)

    def __str__(self) -> str:
        """Return a compact labeled representation of the matrix."""
        row_labels = list(self.rows.keys())
        col_labels = list(self.cols.keys())

        if len(row_labels) > 10:
            row_labels = row_labels[:5] + ["..."] + row_labels[-5:]
        if len(col_labels) > 10:
            col_labels = col_labels[:5] + ["..."] + col_labels[-5:]

        header = "     " + " ".join(f"{col!s:>8}" for col in col_labels) + "\n"
        rows_str = ""
        for row in row_labels:
            if row == "...":
                rows_str += f"{row:>4} {'...':>8} {'...':>8} {'...':>8}\n"
                continue
            row_data = " ".join(f"{self[row, col]:>8.2f}" if col != "..." else "..." for col in col_labels)
            rows_str += f"{row!s:>4} {row_data}\n"
        return header + rows_str

    def __neg__(self) -> MatrixOD:
        """Return a matrix with all values negated."""
        return MatrixOD(self.rows, self.cols, init=-self.mat, mode=self.mode)

    def __add__(self, other: int | float | MatrixOD) -> MatrixOD:
        """Add a scalar or an aligned matrix.

        Args:
            other: Scalar or matrix to add.

        Returns:
            A new matrix containing the sum.
        """
        if isinstance(other, MatrixOD):
            self._ensure_same_labels(other)
            return MatrixOD(self.rows, self.cols, init=self.mat + other.mat, mode=self.mode)
        if isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            return MatrixOD(self.rows, self.cols, init=self.mat + other, mode=self.mode)
        raise TypeError("Unsupported operand type for addition.")

    __radd__ = __add__

    def __sub__(self, other: int | float | MatrixOD) -> MatrixOD:
        """Subtract a scalar or an aligned matrix.

        Args:
            other: Scalar or matrix to subtract.

        Returns:
            A new matrix containing the difference.
        """
        if isinstance(other, MatrixOD):
            self._ensure_same_labels(other)
            return MatrixOD(self.rows, self.cols, init=self.mat - other.mat, mode=self.mode)
        if isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            return MatrixOD(self.rows, self.cols, init=self.mat - other, mode=self.mode)
        raise TypeError("Unsupported operand type for subtraction.")

    def __rsub__(self, other: int | float) -> MatrixOD:
        """Subtract this matrix from a scalar.

        Args:
            other: Scalar from which to subtract the matrix.

        Returns:
            A new matrix containing the difference.
        """
        if isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            return MatrixOD(self.rows, self.cols, init=other - self.mat, mode=self.mode)
        raise TypeError("Unsupported operand type for subtraction.")

    def __iadd__(self, other: int | float | MatrixOD) -> MatrixOD:
        """Add a scalar or aligned matrix in place.

        Args:
            other: Scalar or matrix to add.

        Returns:
            This matrix after the update.
        """
        if isinstance(other, MatrixOD):
            self._ensure_same_labels(other)
            self.mat += other.mat
        elif isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            self.mat += other
        else:
            raise TypeError("Unsupported operand type for addition.")
        return self

    def __isub__(self, other: int | float | MatrixOD) -> MatrixOD:
        """Subtract a scalar or aligned matrix in place.

        Args:
            other: Scalar or matrix to subtract.

        Returns:
            This matrix after the update.
        """
        if isinstance(other, MatrixOD):
            self._ensure_same_labels(other)
            self.mat -= other.mat
        elif isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            self.mat -= other
        else:
            raise TypeError("Unsupported operand type for subtraction.")
        return self

    def __mul__(self, other: int | float | MatrixOD) -> MatrixOD:
        """Multiply by a scalar or aligned matrix element-wise.

        Args:
            other: Scalar or matrix multiplier.

        Returns:
            A new matrix containing the product.
        """
        if isinstance(other, MatrixOD):
            self._ensure_same_labels(other)
            return MatrixOD(self.rows, self.cols, init=self.mat * other.mat, mode=self.mode)
        if isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            return MatrixOD(self.rows, self.cols, init=self.mat * other, mode=self.mode)
        raise TypeError("Unsupported operand type for multiplication.")

    __rmul__ = __mul__

    def __imul__(self, other: int | float | MatrixOD) -> MatrixOD:
        """Multiply by a scalar or aligned matrix in place.

        Args:
            other: Scalar or matrix multiplier.

        Returns:
            This matrix after the update.
        """
        if isinstance(other, MatrixOD):
            self._ensure_same_labels(other)
            self.mat *= other.mat
        elif isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            self.mat *= other
        else:
            raise TypeError("Unsupported operand type for multiplication.")
        return self

    def __truediv__(self, other: int | float | MatrixOD) -> MatrixOD:
        """Divide by a scalar or aligned matrix element-wise.

        Args:
            other: Scalar or matrix divisor.

        Returns:
            A new matrix containing the quotient.
        """
        if isinstance(other, MatrixOD):
            self._ensure_same_labels(other)
            return MatrixOD(self.rows, self.cols, init=self.mat / other.mat, mode=self.mode)
        if isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            return MatrixOD(self.rows, self.cols, init=self.mat / other, mode=self.mode)
        raise TypeError("Unsupported operand type for division.")

    def __rtruediv__(self, other: int | float) -> MatrixOD:
        """Divide a scalar by this matrix element-wise.

        Args:
            other: Scalar numerator.

        Returns:
            A new matrix containing the quotient.
        """
        if isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            return MatrixOD(self.rows, self.cols, init=other / self.mat, mode=self.mode)
        raise TypeError("Unsupported operand type for division.")

    def __itruediv__(self, other: int | float | MatrixOD) -> MatrixOD:
        """Divide by a scalar or aligned matrix in place.

        Args:
            other: Scalar or matrix divisor.

        Returns:
            This matrix after the update.
        """
        if isinstance(other, MatrixOD):
            self._ensure_same_labels(other)
            self.mat /= other.mat
        elif isinstance(other, (int, float)):  # pyright: ignore[reportUnnecessaryIsInstance]
            self.mat /= other
        else:
            raise TypeError("Unsupported operand type for division.")
        return self

    def transpose(self) -> MatrixOD:
        """Return a transposed matrix with rows and columns swapped."""
        return MatrixOD(self.cols, self.rows, init=self.mat.T, mode=self.mode)

    def inverse(self) -> MatrixOD:
        """Return the inverse of a square matrix."""
        if self.mat.shape[0] != self.mat.shape[1]:
            raise ValueError("Matrix must be square to find its inverse.")
        return MatrixOD(self.rows, self.cols, init=np.linalg.inv(self.mat), mode=self.mode)

    def get_diagonal(self) -> np.ndarray:
        """Return the main diagonal values."""
        return np.diag(self.mat)

    def set_diagonal(self, values: Sequence[float]) -> None:
        """Replace the main diagonal values.

        Args:
            values: Values assigned to the main diagonal.
        """
        if len(values) != min(self.mat.shape):
            raise ValueError("Length of values must match the length of the matrix diagonal.")
        np.fill_diagonal(self.mat, values)

    def nan_to_num(
        self,
        copy: bool = True,
        nan: float = 0.0,
        posinf: float | None = None,
        neginf: float | None = None,
    ) -> None:
        """Replace NaN and infinite values in the matrix.

        Args:
            copy: Whether to return a new array instead of updating in place.
            nan: Replacement value for NaN entries.
            posinf: Replacement value for positive infinity entries.
            neginf: Replacement value for negative infinity entries.
        """
        self.mat = np.nan_to_num(self.mat, copy=copy, nan=nan, posinf=posinf, neginf=neginf)

    def sum(self, axis: int | None = None) -> float | MatrixOD:
        """Sum all values, rows, or columns.

        ``axis=None`` returns a scalar. ``axis=0`` returns one ``sum`` row with
        column totals. ``axis=1`` returns one ``sum`` column with row totals.

        Args:
            axis: Axis to collapse, or ``None`` to sum all values.

        Returns:
            A scalar total or a labeled matrix of axis totals.
        """
        if axis is None:
            return float(np.sum(self.mat))
        if axis == 0:
            summed_cols = np.sum(self.mat, axis=0)[np.newaxis, :]
            return MatrixOD(["sum"], self.cols, init=summed_cols, mode=self.mode)
        if axis == 1:
            summed_rows = np.sum(self.mat, axis=1)[:, np.newaxis]
            return MatrixOD(self.rows, ["sum"], init=summed_rows, mode=self.mode)
        raise ValueError("Axis must be 0, 1, or None.")

    @staticmethod
    def read_df(
        rows: LabelsInput,
        cols: LabelsInput,
        df: pd.DataFrame,
        o_field: str = "o",
        d_field: str = "d",
        value_field: str = "value",
    ) -> MatrixOD:
        """Create a matrix from a long-form DataFrame.

        Args:
            rows: Row labels or a label-to-position mapping.
            cols: Column labels or a label-to-position mapping.
            df: DataFrame containing origin, destination, and value columns.
            o_field: Name of the origin column.
            d_field: Name of the destination column.
            value_field: Name of the value column.

        Returns:
            A matrix populated from ``df``.
        """
        matrix = MatrixOD(rows=rows, cols=cols)
        frame = df[[o_field, d_field, value_field]].rename(columns={o_field: "o", d_field: "d", value_field: "value"})
        for origin, destination, value in frame.itertuples(index=False, name=None):
            matrix[origin, destination] = value
        return matrix

    @staticmethod
    def read_csv(
        rows: LabelsInput,
        cols: LabelsInput,
        file: str | PathLike[str],
        o_field: str = "o",
        d_field: str = "d",
        value_field: str = "value",
    ) -> MatrixOD:
        """Create a matrix from a long-form CSV file.

        Args:
            rows: Row labels or a label-to-position mapping.
            cols: Column labels or a label-to-position mapping.
            file: CSV path or path-like object.
            o_field: Name of the origin column.
            d_field: Name of the destination column.
            value_field: Name of the value column.

        Returns:
            A matrix populated from the CSV file.
        """
        df = pd.read_csv(file, usecols=[o_field, d_field, value_field])
        return MatrixOD.read_df(
            rows=rows,
            cols=cols,
            df=df,
            o_field=o_field,
            d_field=d_field,
            value_field=value_field,
        )

    def write_df(
        self,
        o_field: str = "o",
        d_field: str = "d",
        value_field: str = "value",
    ) -> pd.DataFrame:
        """Return the matrix as a long-form DataFrame.

        Args:
            o_field: Name of the origin column in the result.
            d_field: Name of the destination column in the result.
            value_field: Name of the value column in the result.

        Returns:
            A DataFrame with one row for each origin-destination pair.
        """
        data: list[dict[str, Any]] = []
        for origin, origin_index in self.rows.items():
            for destination, destination_index in self.cols.items():
                data.append(
                    {
                        o_field: origin,
                        d_field: destination,
                        value_field: self.mat[origin_index, destination_index],
                    }
                )
        return pd.DataFrame(data)

    def write_csv(
        self,
        file: str | PathLike[str],
        o_field: str = "o",
        d_field: str = "d",
        value_field: str = "value",
    ) -> None:
        """Write the matrix as a long-form CSV file.

        Args:
            file: CSV path or path-like object.
            o_field: Name of the origin column.
            d_field: Name of the destination column.
            value_field: Name of the value column.
        """
        df = self.write_df(o_field=o_field, d_field=d_field, value_field=value_field)
        df.to_csv(file, index=False)
