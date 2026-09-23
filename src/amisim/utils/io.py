import re
from typing import Any, TypeAlias
from gataframe import GataFrame, Engine, GataSourceType
from numpy import dtype
from pandas import DataFrame
from geopandas import GeoDataFrame
from collections import defaultdict
from pathlib import Path


MappingType: TypeAlias = dict[str, str] | None
DTypeType: TypeAlias = str | dict[str, str | dict[str, str | None]] | None
CRSType: TypeAlias = dict[str, str] | str | None
TZType: TypeAlias = dict[str, str] | None
FieldDefinitionType: TypeAlias = dict[str, dict[str, Any]] | None


def read_source(
    engine: Engine,
    source: GataSourceType,
    format: str | None = None,
    mapping: MappingType = None,
    pre_filter: str | None = None,
    filter: list[str] | str | None = None,
    dtype: DTypeType = None,
    geometry_column: str | None = None,
    crs: CRSType = None,
    limit: int | None = None,
    pre_limit: int | None = None,
    additional_fields: FieldDefinitionType = None,
    tz: TZType = None,
    suppress_geometry_default_warnings: bool = False,
    suppress_crs_not_specified_warnings: bool = False,
) -> DataFrame | GeoDataFrame:

    gf: GataFrame | None = engine.read(
        source=source, format=format, limit=limit, pre_filter=pre_filter, pre_limit=pre_limit
    )

    if gf is None:
        raise ValueError(f"Failed to read source: {source}")

    if mapping is not None:
        inverse_mapping = defaultdict(list)
        source_cols_or_expressions = list(mapping.values())
        for target_col, source_col in mapping.items():
            inverse_mapping[source_col].append(target_col)

        # estraggo le colonne sempliciemente calcoate controllando con le espressioni regolari quali sono composte da
        # caratteri ammessi per il nome delle colonne anche gli doppi apici
        regular_columns_pattern = r'^"?[a-zA-Z_][a-zA-Z0-9_]*"?$'
        regular_columns = [col for col in source_cols_or_expressions if re.match(regular_columns_pattern, col)]
        calculated_columns = [col for col in source_cols_or_expressions if col not in regular_columns]
        _temp_mapping = {f"__tmp_{i}__": col for i, col in enumerate(calculated_columns)}

        # creeo le nuove colonne calcolate con nomi temporanei
        if _temp_mapping:
            gf = gf.withColumn(_temp_mapping)
            # aggiorno la mappatura inversa con i nomi temporanei
            for source_col, target_cols in inverse_mapping.items():
                for i, target_col in enumerate(target_cols):
                    if target_col in _temp_mapping:
                        inverse_mapping[source_col][i] = f"__tmp_{list(_temp_mapping.keys()).index(target_col)}__"

        # rinomino le colonne regolari con i nomi target
        if regular_columns:
            to_rename = {}
            new_names = {col: inverse_mapping[col] for col in regular_columns}
            for target_col, source_cols in new_names.items():
                for source_col in source_cols:
                    if source_col in gf.columns:
                        to_rename[source_col] = target_col
            gf = gf.withColumn(to_rename)

        # rinomino le colonne temporanee con i nomi target
        if _temp_mapping:
            to_rename = {}
            temp_rename = {f"__tmp_{i}__": inverse_mapping[col] for i, col in enumerate(calculated_columns)}
            for target_col, source_cols in temp_rename.items():
                for i, source_col in enumerate(source_cols):
                    if target_col in gf.columns:
                        to_rename[source_col] = target_col
            gf = gf.withColumn(to_rename)
            gf = gf.dropColumn(list(_temp_mapping.keys()))
            if gf is None:
                raise ValueError(f"Failed to rename temporary columns in GataFrame")

    if dtype is not None:
        normalized_dtype: DTypeType
        if isinstance(dtype, str):
            normalized_dtype = {col_name: dtype for col_name in gf.columns}
        else:
            normalized_dtype = dict(dtype)

        for col_name in normalized_dtype:
            # se è un istante temporale gli associo la timezone

            target_type = normalized_dtype[col_name]
            if isinstance(target_type, str) and target_type.lower() in {"timestamp", "timestamptz"}:
                normalized_dtype[col_name] = {
                    "type": target_type,
                    "tz": tz.get(col_name) if tz and tz.get(col_name) else None,
                }
            elif isinstance(target_type, dict) and str(target_type.get("type", "")).lower() in {
                "timestamp",
                "timestamptz",
            }:
                if tz is not None:
                    ttz = tz.get(col_name)
                    if ttz is not None and isinstance(ttz, str):
                        target_type.setdefault("tz", ttz)

        gf = gf.as_type({k: v for k, v in normalized_dtype.items() if k in gf.columns})

    if additional_fields is not None:
        for col_name, spec in additional_fields.items():
            value = spec.get("value", "NULL")
            target_type = spec.get("dtype", "string")
            override = spec.get("override", False)
            if not override and col_name in gf.columns:
                continue
            spec_target_type = target_type
            # se è un istante temporale gli associo la timezone
            if isinstance(target_type, str) and target_type.lower() in {"timestamp", "timestamptz"}:
                spec_target_type = {
                    "type": target_type,
                    "tz": tz.get(col_name) if tz and tz.get(col_name) else None,
                }
            elif isinstance(target_type, dict) and str(target_type.get("type", "")).lower() in {
                "timestamp",
                "timestamptz",
            }:
                spec_target_type = target_type.copy()
                spec_target_type.setdefault("tz", tz.get(col_name) if tz and tz.get(col_name) else None)

            gf = gf.withColumn(cols=col_name, expr=value)
            if spec_target_type:
                gf = gf.as_type({col_name: spec_target_type})

    if filter is not None:
        if isinstance(filter, list):
            for f in filter:
                gf = gf.filter(f)
        else:
            gf = gf.filter(filter)

    df = gf.toPandasOrGeoPandas(
        geometry=geometry_column,
        crs=crs,
        suppress_geometry_default_warnings=suppress_geometry_default_warnings,
        suppress_crs_not_specified_warnings=suppress_crs_not_specified_warnings,
    )
    if df is None:
        raise ValueError(f"Failed to convert GataFrame to DataFrame/GeoDataFrame")
    if dtype is not None:
        if isinstance(dtype, str):
            normalized_dtype = {col_name: dtype for col_name in df.columns}
        else:
            normalized_dtype = dict(dtype)
        pandas_dtype_mapping = {}
        for col_name in normalized_dtype:
            # se è un istante temporale gli associo la timezone
            target_type = normalized_dtype[col_name]
            if isinstance(target_type, str) and target_type.lower() in {"timestamp", "timestamptz"}:
                tz_value = tz.get(col_name) if tz and tz.get(col_name) else None
                normalized_dtype[col_name] = {
                    "type": target_type,
                    "tz": tz_value,
                }
                pandas_dtype_mapping[col_name] = "datetime64[ns]"
            elif isinstance(target_type, dict) and str(target_type.get("type", "")).lower() in {
                "timestamp",
                "timestamptz",
            }:
                if tz is not None:
                    ttz = tz.get(col_name)
                    if ttz is not None and isinstance(ttz, str):
                        target_type.setdefault("tz", ttz)
                pandas_dtype_mapping[col_name] = "datetime64[ns]"
        for col_name, dtype in pandas_dtype_mapping.items():
            if dtype is not None and col_name in df.columns:
                if dtype == "datetime64[ns]":
                    col_dtype = normalized_dtype.get(col_name, {}) or {}
                    tz_value = col_dtype.get("tz") if isinstance(col_dtype, dict) else None
                    if tz_value is not None:
                        df[col_name] = df[col_name].dt.tz_convert(tz_value)

    return df
