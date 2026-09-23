from __future__ import annotations
from abc import abstractmethod, ABC
from .base_model import BaseModel

from enum import Enum
from gataframe import Engine, SourceFormatEnum
from geopandas import GeoDataFrame
import pandas as pd
from pandas import DataFrame
from pathlib import Path
from ..utils.io import read_source
from typing import Any, TypeAlias
from .parsers import parse_set

_ResultType: TypeAlias = DataFrame | GeoDataFrame | None


class Matrix(BaseModel):
    field_definition: dict[str, Any] | None = {
        "o": {"mapping": "o", "dtype": "Int64", "required": True},
        "d": {"mapping": "d", "dtype": "Int64", "required": True},
        "timestamp": {"mapping": "timestamp", "dtype": "Float32", "required": True},
        "value": {"mapping": "value", "dtype": "Float32", "required": True}
    }

    def __init__(self):
        super().__init__()

    @classmethod
    def parse(cls, source: _ResultType) -> BaseModel:
        ret = cls()
        ret.df = source
        return ret

    def __iadd__(self, other: BaseModel) -> BaseModel:
        # somma i valori di self.df e other.df basandosi sugli indici ["o", "d", "timestamp"]
        if self.df is None or other.df is None:
            return self
        tmp = self.df.set_index(["o", "d", "timestamp"])
        other_tmp = other.df.set_index(["o", "d", "timestamp"])
        tmp = tmp.add(other_tmp, fill_value=0)
        self.df = tmp.reset_index()
        return self

    def __isub__(self, other: BaseModel) -> BaseModel:
        # sottrae i valori di other.df da self.df basandosi sugli indici ["o", "d", "timestamp"]
        if self.df is None or other.df is None:
            return self
        tmp = self.df.set_index(["o", "d", "timestamp"])
        other_tmp = other.df.set_index(["o", "d", "timestamp"])
        tmp = tmp.sub(other_tmp, fill_value=0)
        self.df = tmp.reset_index()
        return self

    def __imul__(self, other: BaseModel) -> BaseModel:
        # moltiplica i valori di self.df per quelli di other.df basandosi sugli indici ["o", "d", "timestamp"]
        if self.df is None or other.df is None:
            return self
        tmp = self.df.set_index(["o", "d", "timestamp"])
        other_tmp = other.df.set_index(["o", "d", "timestamp"])
        tmp = tmp.mul(other_tmp, fill_value=0)
        self.df = tmp.reset_index()
        return self

    def __itruediv__(self, other: BaseModel) -> BaseModel:
        # divide i valori di self.df per quelli di other.df basandosi sugli indici ["o", "d", "timestamp"]
        if self.df is None or other.df is None:
            return self
        tmp = self.df.set_index(["o", "d", "timestamp"])
        other_tmp = other.df.set_index(["o", "d", "timestamp"])
        tmp = tmp.div(other_tmp, fill_value=0)
        self.df = tmp.reset_index()
        return self
