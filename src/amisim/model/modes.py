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

ModeType: TypeAlias = dict[str, dict[str, Any]] | None

class Modes(BaseModel):
    field_definition: dict[str, Any] | None = {
        "code": {"mapping": "code", "dtype": "str", "required": True},
        "description": {"mapping": "description", "dtype": "str", "required": False},
        "eq_factor": {"mapping": "eq_factor", "dtype": "float", "required": False},
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
        tmp = self.df.set_index(["code"])
        other_tmp = other.df.set_index(["code"])
        tmp[tmp.index.isin(other_tmp.index)] = other_tmp.loc[tmp.index.isin(other_tmp.index)]
        new_rows = other_tmp[~other_tmp.index.isin(tmp.index)]
        self.df = pd.concat([tmp, new_rows]).reset_index()
        return self

    def __isub__(self, other: BaseModel) -> BaseModel:
        # rimuove le righe presenti in other dal DataFrame corrente
        if self.df is None or other.df is None:
            return self
        tmp = self.df.set_index(["code"])
        other_tmp = other.df.set_index(["code"])
        tmp = tmp[~tmp.index.isin(other_tmp.index)]
        self.df = tmp.reset_index()
        return self

    def __imul__(self, other: BaseModel) -> BaseModel:
        raise NotImplementedError("The __imul__ method must be implemented by the subclass.")

    def __itruediv__(self, other: BaseModel) -> BaseModel:
        raise NotImplementedError("The __itruediv__ method must be implemented by the subclass.")
