import pandas as pd
import json


def parse_set(series: pd.Series) -> pd.Series:
    if pd.api.types.is_string_dtype(series):
        try:
            return pd.Series(
                [set(x.split(",")) if pd.notna(x) else None for x in series],
                index=series.index,
            )
        except ValueError:
            raise ValueError(f"Invalid set string: {series}")
    return series


def parse_json(series: pd.Series) -> pd.Series:
    if pd.api.types.is_string_dtype(series):
        try:
            return pd.Series(
                [json.loads(x) if pd.notna(x) and x else None for x in series],
                index=series.index,
            )
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON string: {series}")
    return series
