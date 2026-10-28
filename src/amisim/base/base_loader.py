"""Base loader infrastructure: input/output parameters and read/write logic."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TypeAlias

import numpy as np
from gataframe import Engine, GataFrame, GataSourceType, SourceFormatEnum
from geopandas import GeoDataFrame
from pandas import DataFrame, Series, isna

from ..utils import DictMixin

DictParamsType: TypeAlias = dict[str, Any]
DataFormatEnum: TypeAlias = str | SourceFormatEnum
DataSourceType: TypeAlias = str | Path | DataFrame | GeoDataFrame | DictParamsType
DataDestinationType: TypeAlias = str | Path
DataResultType: TypeAlias = DataFrame | GeoDataFrame

MappingType: TypeAlias = dict[str, str]
DTypeType: TypeAlias = str | dict[str, str | dict[str, str | None]]
CRSType: TypeAlias = dict[str, str] | str
TZType: TypeAlias = dict[str, str] | str
FieldDefinitionType: TypeAlias = dict[str, dict[str, Any]]
ParsersType: TypeAlias = dict[str, Callable[[Series], Series]]

__all__ = [
    "DataResultType",
    "DataSourceType",
    "DataDestinationType",
    "DataFormatEnum",
    "MappingType",
    "DTypeType",
    "CRSType",
    "TZType",
    "FieldDefinitionType",
    "ParsersType",
    "OutputParameters",
    "InputParameters",
    "BaseLoader",
    "read_source",
]


@dataclass
class OutputParameters(DictMixin):
    """Parameters describing where and how a dataframe is written."""

    destination: DataDestinationType | None = None
    src: DataDestinationType | None = None  # alias for destination
    mode: str | None = None
    partitionBy: list[str] | str | None = None
    pk: str | list[str] | None = None
    index: str | list[str] | None = None
    n_partitions: int | None = None
    geometry: str | None = None
    crs_source: CRSType | None = None
    crs_target: CRSType | None = None
    hive_partitioning: bool | None = None
    format: str | DataFormatEnum | None = None

    def __post_init__(self):
        if self.src is None:
            self.src = self.destination
        if self.destination is None:
            self.destination = self.src

    @classmethod
    def parse(
        cls, output_parameters: DataDestinationType | OutputParameters | DictParamsType | None
    ) -> OutputParameters:
        """Normalize `output_parameters` into an `OutputParameters` instance.

        Args:
            output_parameters: Instance or dictionary to normalize.

        Returns:
            The parsed output parameters.

        Raises:
            ValueError: If `output_parameters` is `None`.
            TypeError: If the type is not supported.
        """
        if output_parameters is None:
            raise ValueError("Output parameters cannot be None.")
        elif isinstance(output_parameters, OutputParameters):
            return output_parameters
        elif isinstance(output_parameters, dict):
            return cls.from_dict(output_parameters)
        elif isinstance(output_parameters, DataDestinationType):
            return cls(destination=output_parameters)
        else:
            raise TypeError(f"Unsupported output parameters type: {type(output_parameters)!r}")


@dataclass
class InputParameters(DictMixin):
    """Parameters describing a source to read and how to normalize it."""

    src: DataSourceType | list[DataSourceType] | None = None
    destination: DataSourceType | list[DataSourceType] | None = None  # alias for src
    format: str | SourceFormatEnum | None = None
    mapping: MappingType | None = None
    pre_filter: str | None = None
    filter: list[str] | str | None = None
    dtype: DTypeType | None = None
    geometry: str | None = None
    crs: CRSType | None = None
    limit: int | None = None
    pre_limit: int | None = None
    layer: str | None = None
    tz_data: TZType | None = None
    additional_fields: FieldDefinitionType | None = None
    operation: str | None = None

    def __post_init__(self):
        if self.destination is None:
            self.destination = self.src
        if self.src is None:
            self.src = self.destination

    @classmethod
    def parse(
        cls,
        input_parameters: InputParameters
        | DataSourceType
        | list[InputParameters | DataSourceType]
        | list[InputParameters]
        | list[DataSourceType],
    ) -> InputParameters | list[InputParameters]:
        """Parse.

        Args:
            input_parameters: Instance, dictionary, source or list of them.

        Returns:
            A single instance, or a list when several sources are given.

        Raises:
            ValueError: If `input_parameters` is `None`.
            TypeError: If the type is not supported.

        """
        if input_parameters is None:
            raise ValueError("Input parameters cannot be None.")
        elif isinstance(input_parameters, InputParameters):
            return input_parameters
        elif isinstance(input_parameters, dict):
            return cls.from_dict(input_parameters)
        elif isinstance(input_parameters, (str, Path, DataFrame, GeoDataFrame)):
            return cls(src=input_parameters)
        elif isinstance(input_parameters, list):
            parsed_parameters: list[InputParameters] = []
            if len(input_parameters) > 0 and isinstance(input_parameters[0], dict) and not "src" in input_parameters[0]:
                df = DataFrame(input_parameters)
                return cls(src=df)
            for param in input_parameters:
                parsed = cls.parse(param)
                if isinstance(parsed, list):
                    parsed_parameters.extend(parsed)
                else:
                    parsed_parameters.append(parsed)
            return parsed_parameters
        raise TypeError(f"Unsupported input parameters type: {type(input_parameters)!r}")

    def add_filter(self, filter_condition: list[str] | str) -> None:
        """Add filter.

        Args:
            filter_condition: Condition, or list of conditions, to append to the
                current filters.

        """
        if not hasattr(self, "filter") or self.filter is None:
            self.filter = []
        if isinstance(self.filter, str):
            self.filter = [self.filter]
        if isinstance(filter_condition, list):
            self.filter.extend(filter_condition)
        else:
            self.filter.append(filter_condition)


InputType: TypeAlias = (
    InputParameters
    | DataSourceType
    | list[InputParameters | DataSourceType]
    | list[InputParameters]
    | list[DataSourceType]
)

OutputType: TypeAlias = DataDestinationType | OutputParameters | DictParamsType


class BaseLoader(ABC):
    """Read, normalize and write the dataframes of a model entity."""

    field_definition: FieldDefinitionType | None = None
    additional_fields: FieldDefinitionType | None = None

    _default_mapping: MappingType | None = None
    _default_dtype: DTypeType | None = None
    _default_tz_data: TZType | None = None
    _default_crs: CRSType | None = None
    _default_parsers: ParsersType | None = None
    _default_default: dict[str, Any] | None = None
    _default_required: dict[str, bool] | None = None

    def __init__(self):
        """Resolve the field definition defaults and reset the dataframe."""
        self._parse_fields_definition()
        self.df: DataResultType | None = None

    @classmethod
    def _parse_fields_definition(cls) -> None:
        # Internal helper: parse fields definition.
        """Internal helper: parse fields definition."""
        if cls.field_definition is not None:
            cls._default_mapping = cls._default_mapping or {}
            cls._default_dtype = cls._default_dtype or {}
            cls._default_tz_data = cls._default_tz_data or {}
            cls._default_crs = cls._default_crs or {}
            cls._default_parsers = cls._default_parsers or {}
            cls._default_default = cls._default_default or {}
            cls._default_required = cls._default_required or {}

            total_fields = cls.field_definition.copy()
            total_fields.update(cls.additional_fields or {})

            for field, definition in total_fields.items():
                if mapping := definition.get("mapping"):
                    if definition.get("required"):
                        cls._default_required.setdefault(field, mapping)
                if dtype := definition.get("dtype"):
                    if isinstance(cls._default_dtype, str):
                        cls._default_dtype = {}
                    cls._default_dtype.setdefault(field, dtype)
                if tz_data := definition.get("tz_data"):
                    if isinstance(cls._default_tz_data, str):
                        cls._default_tz_data = {}
                    cls._default_tz_data.setdefault(field, tz_data)
                if crs := definition.get("crs"):
                    if isinstance(cls._default_crs, str):
                        cls._default_crs = {}
                    cls._default_crs.setdefault(field, crs)
                if parser := definition.get("parser"):
                    cls._default_parsers.setdefault(field, parser)
                if default := definition.get("default"):
                    cls._default_default.setdefault(field, default)
                if required := definition.get("required"):
                    cls._default_required.setdefault(field, required)

    @classmethod
    @abstractmethod
    def parse(cls, source: DataResultType) -> BaseLoader:
        """Parse.

        Args:
            source: Dataframe to validate and normalize.

        Returns:
            The loader holding the parsed dataframe.

        """
        raise NotImplementedError("The parse method must be implemented by the subclass.")

    @abstractmethod
    def __iadd__(self, other: BaseLoader) -> BaseLoader:
        """Merge `other` into this loader by adding its rows.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        raise NotImplementedError("The __iadd__ method must be implemented by the subclass.")

    @abstractmethod
    def __isub__(self, other: BaseLoader) -> BaseLoader:
        """Merge `other` into this loader by subtracting its rows.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        raise NotImplementedError("The __isub__ method must be implemented by the subclass.")

    @abstractmethod
    def __imul__(self, other: BaseLoader) -> BaseLoader:
        """Merge `other` into this loader by multiplying its values.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        raise NotImplementedError("The __imul__ method must be implemented by the subclass.")

    @abstractmethod
    def __itruediv__(self, other: BaseLoader) -> BaseLoader:
        """Merge `other` into this loader by dividing its values.

        Args:
            other: Loader whose data is combined with this one.

        Returns:
            This loader after the merge.

        """
        raise NotImplementedError("The __itruediv__ method must be implemented by the subclass.")

    @classmethod
    def read(cls, engine: Engine, params: InputType, additional_filters: list[str] | str | None = None) -> BaseLoader:
        """Read.

        Args:
            engine: Engine used to read the sources.
            params: Source parameters, single or as a list.
            additional_filters: Extra filter conditions applied to every source.

        Returns:
            The loader holding the read dataframe.

        Raises:
            ValueError: If `params` is `None`.

        """
        if params is None:
            raise ValueError("Params cannot be None")
        params = InputParameters.parse(params)
        if additional_filters is not None:
            if isinstance(params, list):
                for p in params:
                    p.add_filter(additional_filters)
            else:
                params.add_filter(additional_filters)
        if isinstance(params, list):
            return cls._read_from_list(engine=engine, source_list=params)  # type: ignore
        else:
            return cls._read_from_params(engine=engine, params=params)

    @classmethod
    def write(cls, engine: Engine, df: DataFrame, params: OutputType | None, mode: str | None = None) -> None:
        """Write `df` to the destination described by `params`.

        Args:
            engine: Engine used to write the dataframe.
            df: Dataframe to write.
            params: Output parameters, already parsed or as a dictionary.
            mode: Mode to use for writing, overrides `params.mode` if provided.

        Raises:
            ValueError: If `params` is `None`.
        """
        if params is None:
            raise ValueError("Params cannot be None")
        params = OutputParameters.parse(params)
        if mode is not None:
            params.mode = mode
        return cls._write_from_params(engine=engine, df=df, params=params)

    @classmethod
    def _write_from_params(cls, engine: Engine, df: DataFrame, params: OutputParameters) -> None:
        """Internal helper: write a dataframe from parsed output parameters."""
        from ..amisim_app import AmisimApp

        if df is None:
            raise ValueError("DataFrame 'df' cannot be None")
        _destination = params.destination
        if _destination is None:
            raise ValueError('Destination "destination" cannot be None')
        _mode = params.mode
        if _mode is None:
            _mode = "overwrite"
        _partitionBy = params.partitionBy
        _pk = params.pk
        _index = params.index
        _n_partitions = params.n_partitions
        _geometry = params.geometry
        if _geometry is None:
            if isinstance(df, GeoDataFrame):
                _geometry = str(df.geometry.name)
            else:
                _geometry = "geometry"
        _crs_source = params.crs_source
        if _crs_source is None:
            _crs_source = {_geometry: AmisimApp.get_instance().ini.GENERAL.CRS_CALC}
        _crs_target = params.crs_target
        if _crs_target is None:
            _crs_target = {_geometry: AmisimApp.get_instance().ini.GENERAL.CRS}
        _hive_partitioning = params.hive_partitioning
        if _hive_partitioning is None:
            _hive_partitioning = False
        _format = params.format
        if isinstance(_format, Enum):
            _format = _format.value

        engine.write(
            df=df,
            destination=_destination,
            mode=_mode,
            partitionBy=_partitionBy,
            pk=_pk,
            index=_index,
            n_partitions=_n_partitions,
            geometry=_geometry,
            crs_source=_crs_source if isinstance(_crs_source, str) else _crs_source.get(_geometry),
            crs_target=_crs_target if isinstance(_crs_target, str) else _crs_target.get(_geometry),
            hive_partitioning=_hive_partitioning,
            format=_format,
        )

    @classmethod
    def _read_from_params(cls, engine: Engine, params: InputParameters) -> BaseLoader:
        # Internal helper: read from params.
        """Internal helper: read from params."""
        from ..amisim_app import AmisimApp

        cls._parse_fields_definition()
        src = params.src
        if src is None:
            raise ValueError('Source "src" cannot be None')
        if isinstance(src, list):
            raise ValueError('Source "src" cannot be a list in _read_from_params')
        format = params.format
        mapping = params.mapping
        pre_filter = params.pre_filter
        filter = params.filter
        dtype = params.dtype
        geometry = params.geometry
        crs = params.crs
        if crs is None:
            crs = {"geometry": AmisimApp.get_instance().ini.GENERAL.CRS}
        limit = params.limit
        pre_limit = params.pre_limit
        additional_fields = params.additional_fields
        tz_data = params.tz_data

        if cls.additional_fields is not None:
            if additional_fields is None:
                additional_fields = cls.additional_fields
            elif isinstance(additional_fields, dict):
                tmp_additional_fields = cls.additional_fields.copy()
                tmp_additional_fields.update(additional_fields)
                additional_fields = tmp_additional_fields
        if cls._default_mapping is not None:
            if mapping is None:
                mapping = cls._default_mapping
            elif isinstance(mapping, dict):
                tmp_mapping = cls._default_mapping.copy()
                tmp_mapping.update(mapping)
                mapping = tmp_mapping
        if cls._default_dtype is not None:
            if dtype is None:
                dtype = cls._default_dtype
            elif isinstance(dtype, dict) and isinstance(cls._default_dtype, dict):
                tmp_dtype = cls._default_dtype.copy()
                tmp_dtype.update(dtype)
                dtype = tmp_dtype
        if cls._default_crs is not None:
            if crs is None:
                crs = cls._default_crs
            elif isinstance(crs, dict) and isinstance(cls._default_crs, dict):
                tmp_crs = cls._default_crs.copy()
                tmp_crs.update(crs)
                crs = tmp_crs
        if cls._default_tz_data is not None:
            if tz_data is None:
                tz_data = cls._default_tz_data
            elif isinstance(tz_data, dict) and isinstance(cls._default_tz_data, dict):
                tmp_tz_data = cls._default_tz_data.copy()
                tmp_tz_data.update(tz_data)
                tz_data = tmp_tz_data

        from ..amisim_app import AmisimApp

        app = AmisimApp.get_instance()
        df = read_source(
            engine=engine,
            source=src,
            format=format.value if isinstance(format, SourceFormatEnum) else format,
            mapping=mapping,
            pre_filter=pre_filter,
            filter=filter,
            dtype=dtype,
            geometry_column=geometry,
            crs=crs,
            limit=limit,
            pre_limit=pre_limit,
            additional_fields=additional_fields,
            tz=tz_data,
            crs_target=app.ini.GENERAL.CRS_CALC,
            suppress_geometry_default_warnings=True,
            suppress_crs_not_specified_warnings=True,
        )
        if df is None:
            raise ValueError("Failed to read source into DataFrame")
        ret = cls.parse(df)

        if ret.df is None:
            raise ValueError("Failed to read source into DataFrame")
        for field, required in (cls._default_required or {}).items():
            if required and field not in ret.df.columns:
                ret.df = ret.df.assign(**{field: None})
        for field, default in (cls._default_default or {}).items():
            if field in ret.df.columns and not isna(default):
                if default == "autoincrement":
                    max_value = ret.df[field].max() if not ret.df[field].isna().all() else 0
                    ret.df[field] = np.where(ret.df[field].isna(), ret.df.index.values + max_value + 1, ret.df[field])
                else:
                    ret.df.fillna({field: default}, inplace=True)
        for field, parser in (cls._default_parsers or {}).items():
            if field in ret.df.columns:
                ret.df[field] = parser(ret.df[field])
        return ret

    @classmethod
    def _read_from_list(cls, engine: Engine, source_list: list[InputParameters], **kwargs) -> BaseLoader:
        # Internal helper: read from list.
        """Internal helper: read from list."""
        results: list[tuple[BaseLoader, str]] = []
        for source in source_list:
            operation: str = "+"
            if isinstance(source, list):
                result = cls._read_from_list(engine=engine, source_list=source, **kwargs)  # type: ignore
                results.append((result, operation))
            elif isinstance(source, InputParameters):
                operation = source.operation or "+"
                result = cls.read(engine=engine, params=source)
            else:
                raise ValueError(f"Unsupported source type: {type(source)}")
            results.append((result, operation))
        return cls._parse_results(results)

    @classmethod
    def _parse_results(cls, dataframes: list[tuple[BaseLoader, str]]) -> "BaseLoader":
        # Internal helper: parse results.
        """Internal helper: parse results."""
        if not isinstance(dataframes, list):
            return cls.parse(dataframes)

        result: BaseLoader | None = None
        for base_input, op in dataframes:
            if result is None:
                result = base_input
                continue
            if op == "+":
                result += base_input
            elif op == "-":
                result -= base_input
            elif op == "*":
                result *= base_input
            elif op == "/":
                result /= base_input
            else:
                raise ValueError(f"Unsupported operation: {op}")

        if result is None:
            raise ValueError("No dataframes to parse")

        return result


def read_source(
    engine: Engine,
    source: GataSourceType,
    format: str | None = None,
    mapping: MappingType | None = None,
    pre_filter: str | None = None,
    filter: list[str] | str | None = None,
    dtype: DTypeType | None = None,
    geometry_column: str | None = None,
    crs: CRSType | None = None,
    limit: int | None = None,
    pre_limit: int | None = None,
    additional_fields: FieldDefinitionType | None = None,
    tz: TZType | None = None,
    crs_target: CRSType | None = None,
    suppress_geometry_default_warnings: bool = False,
    suppress_crs_not_specified_warnings: bool = False,
) -> DataFrame | GeoDataFrame:
    """Read source.

    Args:
        engine: Engine used to read the source.
        source: Source to read: path, dataframe, query or mapping.
        format: Explicit source format; inferred when omitted.
        mapping: Mapping from source column names to model field names.
        pre_filter: Filter applied by the engine before reading.
        filter: Filter conditions applied to the read dataframe.
        dtype: Target dtypes of the columns.
        geometry_column: Name of the geometry column.
        crs: Coordinate reference system of the geometries.
        limit: Maximum number of rows kept after reading.
        pre_limit: Maximum number of rows read by the engine.
        additional_fields: Extra computed fields to append.
        tz: Timezone of the datetime columns.
        suppress_geometry_default_warnings: Silence the default geometry warnings.
        suppress_crs_not_specified_warnings: Silence the missing CRS warnings.

    Returns:
        The normalized dataframe, as a geodataframe when a geometry is present.

    """
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

        # estraggo le colonne sempliciemente calcolate controllando con le espressioni regolari quali sono composte da
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
                raise ValueError("Failed to rename temporary columns in GataFrame")

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
                _tz = tz.get(col_name) if isinstance(tz, dict) else tz if isinstance(tz, str) else None
                normalized_dtype[col_name] = {
                    "type": target_type,
                    "tz": _tz,
                }
            elif isinstance(target_type, dict) and str(target_type.get("type", "")).lower() in {
                "timestamp",
                "timestamptz",
            }:
                if tz is not None:
                    _tz = tz.get(col_name) if isinstance(tz, dict) else tz if isinstance(tz, str) else None
                    if _tz is not None and isinstance(_tz, str):
                        target_type.setdefault("tz", _tz)
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
                _tz = tz.get(col_name) if isinstance(tz, dict) else tz if isinstance(tz, str) else None
                spec_target_type = {
                    "type": target_type,
                    "tz": _tz,
                }
            elif isinstance(target_type, dict) and str(target_type.get("type", "")).lower() in {
                "timestamp",
                "timestamptz",
            }:
                _tz = tz.get(col_name) if isinstance(tz, dict) else tz if isinstance(tz, str) else None
                spec_target_type = target_type.copy()
                spec_target_type.setdefault("tz", _tz)

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
        raise ValueError("Failed to convert GataFrame to DataFrame/GeoDataFrame")
    if crs_target is not None and isinstance(df, GeoDataFrame):
        df = df.to_crs(crs_target)
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
                _tz = tz.get(col_name) if isinstance(tz, dict) else tz if isinstance(tz, str) else None
                normalized_dtype[col_name] = {
                    "type": target_type,
                    "tz": _tz,
                }
                pandas_dtype_mapping[col_name] = "datetime64[ns]"
            elif isinstance(target_type, dict) and str(target_type.get("type", "")).lower() in {
                "timestamp",
                "timestamptz",
            }:
                if tz is not None:
                    _tz = tz.get(col_name) if isinstance(tz, dict) else tz if isinstance(tz, str) else None
                    if _tz is not None and isinstance(_tz, str):
                        target_type.setdefault("tz", _tz)
                pandas_dtype_mapping[col_name] = "datetime64[ns]"
        for col_name, dtype in pandas_dtype_mapping.items():
            if dtype is not None and col_name in df.columns:
                if dtype == "datetime64[ns]":
                    col_dtype = normalized_dtype.get(col_name, {}) or {}
                    _tz = col_dtype.get("tz") if isinstance(col_dtype, dict) else None
                    if _tz is not None:
                        df[col_name] = df[col_name].dt.tz_convert(_tz)

    return df
