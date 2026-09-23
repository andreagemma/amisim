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


class Links(BaseModel):
    field_definition: dict[str, Any] | None = {
        "from_node": {"mapping": "from_node", "dtype": "Int64", "required": True},
        "to_node": {"mapping": "to_node", "dtype": "Int64", "required": True},
        "v0": {"mapping": "v0", "dtype": "Float32", "required": True},
        "connector": {"mapping": "connector", "dtype": "bool", "required": True},
        "lanes": {"mapping": "lanes", "dtype": "Float32", "required": True},
        "alpha": {"mapping": "alpha", "dtype": "Float32", "required": True, "default": 1.6},
        "rcr": {"mapping": "rcr", "dtype": "Float32", "required": True, "default": 30},
        "capacity": {"mapping": "capacity", "dtype": "Float32", "required": True},
        "length": {"mapping": "length", "dtype": "Float32", "required": True},
        "modes": {"mapping": "mode", "dtype": "str", "required": True, "parser": parse_set},
        "geometry": {"mapping": "geometry", "dtype": "geometry", "required": True},
    }
    additional_fields: dict[str, Any] | None = {
        "t0": {"mapping": "t0", "dtype": "Float32", "override": False, "value": "length / v0 * 60"},
    }

    def __init__(self):
        super().__init__()

    @classmethod
    def parse(cls, source: _ResultType) -> BaseModel:
        ret = cls()
        ret.df = source
        return ret

    def __iadd__(self, other: BaseModel) -> BaseModel:
        # sostituisce i valori esistenti con quelli di other
        # e aggiunge le nuove righe da other
        if self.df is None or other.df is None:
            return self
        tmp = self.df.set_index(["from_node", "to_node"])
        other_tmp = other.df.set_index(["from_node", "to_node"])
        tmp[tmp.index.isin(other_tmp.index)] = other_tmp.loc[tmp.index.isin(other_tmp.index)]
        new_rows = other_tmp[~other_tmp.index.isin(tmp.index)]
        self.df = pd.concat([tmp, new_rows]).reset_index()
        return self

    def __isub__(self, other: BaseModel) -> BaseModel:
        # rimuove le righe presenti in other dal DataFrame corrente
        if self.df is None or other.df is None:
            return self
        tmp = self.df.set_index(["from_node", "to_node"])
        other_tmp = other.df.set_index(["from_node", "to_node"])
        tmp = tmp[~tmp.index.isin(other_tmp.index)]
        self.df = tmp.reset_index()
        return self

    def __imul__(self, other: BaseModel) -> BaseModel:
        raise NotImplementedError("The __imul__ method must be implemented by the subclass.")

    def __itruediv__(self, other: BaseModel) -> BaseModel:
        raise NotImplementedError("The __itruediv__ method must be implemented by the subclass.")
