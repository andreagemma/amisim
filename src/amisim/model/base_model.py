from __future__ import annotations
from abc import abstractmethod, ABC
from pandas import DataFrame, Series, isna
from typing import Callable
from enum import Enum
from gataframe import Engine, SourceFormatEnum
from geopandas import GeoDataFrame
from pandas import DataFrame
from pathlib import Path
from ..utils.io import read_source, MappingType, DTypeType, CRSType, TZType, FieldDefinitionType, GataSourceType
from typing import Any, TypeAlias
from collections import defaultdict
from dataclasses import dataclass
from typing import TypedDict
from ..utils import DictMixin


ResultType: TypeAlias = DataFrame | GeoDataFrame | None
SourceType: TypeAlias = str | Path | DataFrame | GeoDataFrame | dict | None
ParsersType: TypeAlias = dict[str, Callable[[Series], Series]] | None


@dataclass
class InputParameters(DictMixin):
    src: SourceType | list[SourceType] = None
    format: str | SourceFormatEnum | None = None
    mapping: MappingType = None
    pre_filter: str | None = None
    filter: list[str] | str | None = None
    dtype: DTypeType = None
    geometry: str | None = None
    crs: CRSType = None
    limit: int | None = None
    pre_limit: int | None = None
    layer: str | None = None
    tz_data: TZType = None
    additional_fields: FieldDefinitionType = None
    operation: str | None = None

    @classmethod
    def parse(cls, input_parameters: "InputType") -> "InputParameters" | list["InputParameters"]:
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
        if not hasattr(self, "filter") or self.filter is None:
            self.filter = []
        if isinstance(self.filter, str):
            self.filter = [self.filter]
        if isinstance(filter_condition, list):
            self.filter.extend(filter_condition)
        else:
            self.filter.append(filter_condition)


InputType: TypeAlias = (
    InputParameters | SourceType | list[InputParameters | SourceType] | list[InputParameters] | list[SourceType]
)


class BaseModel(ABC):
    field_definition: FieldDefinitionType = None
    additional_fields: FieldDefinitionType = None

    _default_mapping: MappingType = None
    _default_dtype: DTypeType = None
    _default_tz_data: TZType = None
    _default_crs: CRSType = None
    _default_parsers: ParsersType = None
    _default_default: dict[str, Any] | None = None
    _default_required: dict[str, bool] | None = None

    def __init__(self):
        self._parse_fields_definition()
        self.df: ResultType = None

    @classmethod
    def _parse_fields_definition(cls) -> None:
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
    def parse(cls, source: ResultType) -> BaseModel:
        raise NotImplementedError("The parse method must be implemented by the subclass.")

    @abstractmethod
    def __iadd__(self, other: BaseModel) -> BaseModel:
        raise NotImplementedError("The __iadd__ method must be implemented by the subclass.")

    @abstractmethod
    def __isub__(self, other: BaseModel) -> BaseModel:
        raise NotImplementedError("The __isub__ method must be implemented by the subclass.")

    @abstractmethod
    def __imul__(self, other: BaseModel) -> BaseModel:
        raise NotImplementedError("The __imul__ method must be implemented by the subclass.")

    @abstractmethod
    def __itruediv__(self, other: BaseModel) -> BaseModel:
        raise NotImplementedError("The __itruediv__ method must be implemented by the subclass.")

    @classmethod
    def read(cls, engine: Engine, params: InputType, additional_filters: list[str] | str | None = None) -> BaseModel:
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
    def _read_from_params(cls, engine: Engine, params: InputParameters) -> BaseModel:
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
            suppress_geometry_default_warnings=True,
            suppress_crs_not_specified_warnings=True,
        )
        if df is None:
            raise ValueError(f"Failed to read source into DataFrame")
        ret = cls.parse(df)

        if ret.df is None:
            raise ValueError(f"Failed to read source into DataFrame")
        for field, required in (cls._default_required or {}).items():
            if required and field not in ret.df.columns:
                ret.df = ret.df.assign(**{field: None})
        for field, default in (cls._default_default or {}).items():
            if field in ret.df.columns and not isna(default):
                ret.df.fillna({field: default}, inplace=True)
        for field, parser in (cls._default_parsers or {}).items():
            if field in ret.df.columns:
                ret.df[field] = parser(ret.df[field])
        return ret

    @classmethod
    def _read_from_list(cls, engine: Engine, source_list: list[InputParameters], **kwargs) -> BaseModel:
        results: list[tuple[BaseModel, str]] = []
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
    def _parse_results(cls, dataframes: list[tuple[BaseModel, str]]) -> "BaseModel":
        if not isinstance(dataframes, list):
            return cls.parse(dataframes)

        result: BaseModel | None = None
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
