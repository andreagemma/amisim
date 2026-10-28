"""Column parsers used to normalize the values read from the sources."""

import json

import pandas as pd

__all__ = ["parse_set", "parse_list", "parse_json"]


def parse_set(series: pd.Series, subtype: type = str) -> pd.Series:
    """Parse set.

    Args:
        series: Series of `{a,b}` strings to convert.
        subtype: Type of the set elements.

    Returns:
        A series of sets, or the input series if it is not of string dtype.

    Raises:
        ValueError: If a value is not a valid set string.

    """
    if pd.api.types.is_string_dtype(series):
        try:
            return pd.Series(
                [set(x.strip("{}").split(",")) if pd.notna(x) else None for x in series],
                index=series.index,
            )
        except ValueError:
            raise ValueError(f"Invalid set string: {series}")
    return series


def parse_list(series: pd.Series, subtype: type = str) -> pd.Series:
    """Parse list.

    Args:
        series: Series of `[a,b]` strings to convert.
        subtype: Type applied to each element.

    Returns:
        A series of lists, or the input series if it is not of string dtype.

    Raises:
        ValueError: If a value is not a valid list string.

    """
    if pd.api.types.is_string_dtype(series):
        try:
            return pd.Series(
                [[subtype(y) for y in x.strip("[]").split(",")] if pd.notna(x) else None for x in series],
                index=series.index,
            )
        except ValueError:
            raise ValueError(f"Invalid set string: {series}")
    return series


def parse_json(series: pd.Series) -> pd.Series:
    """Parse json.

    Args:
        series: Series of JSON strings to decode.

    Returns:
        A series of decoded objects, or the input series if it is not of string
        dtype.

    Raises:
        ValueError: If a value is not valid JSON.

    """
    if pd.api.types.is_string_dtype(series):
        try:
            return pd.Series(
                [json.loads(x) if pd.notna(x) and x else None for x in series],
                index=series.index,
            )
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON string: {series}")
    return series
