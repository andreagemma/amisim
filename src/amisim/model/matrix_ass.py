from __future__ import annotations

import copy
import warnings
from typing import Any, Generator

import pandas as pd
from scipy.sparse import SparseEfficiencyWarning
from scipy.sparse import csr_matrix as Matrix

from ..base.base_loader import BaseLoader, OutputParameters
from ..base.base_model import BaseModel

warnings.simplefilter("ignore", SparseEfficiencyWarning)

__all__ = ["MatrixAss"]


class MatrixAss(BaseModel):
    class OD:
        def __init__(self, origins: list, destinations: list, detectors: list):
            self.origins = origins
            self.destinations = destinations
            # self.detectors = detectors
            no: int = len(origins)
            nd: int = len(destinations)
            nl: int = len(detectors)

            self.mat: Matrix = Matrix((nl, no * nd))
            self.no: int = no
            self.nd: int = nd
            self.nl: int = nl

        def __getitem__(self, key):
            i, j, l = key
            idx = i * self.nd + j
            return self.mat[l, idx]

        def __setitem__(self, key, value):
            i, j, l = key
            idx = i * self.nd + j
            self.mat[l, idx] = value

        def get_origin_destination(self, idx):
            i = idx // self.nd
            j = idx % self.nd
            return self.origins[i], self.destinations[j]

    def __init__(
        self,
        origins: list,
        destinations: list,
        detectors: list,
        n_intervals: int,
        pre_intervals: int,
    ):

        self.detectors = sorted(detectors, key=str)
        self.origins = sorted(origins)  # pyright: ignore[reportArgumentType]
        self.destinations = sorted(destinations)  # pyright: ignore[reportArgumentType]

        self.n_intervals = n_intervals
        self.pre_intervals = pre_intervals

        self.mats: dict[int, dict[int, MatrixAss.OD]] = {tenter: {} for tenter in range(self.n_intervals)}

        self.o2i = dict([(self.origins[i], i) for i in range(len(self.origins))])
        self.d2i = dict([(self.destinations[i], i) for i in range(len(self.destinations))])
        self.l2i = dict([(self.detectors[i], i) for i in range(len(self.detectors))])

        for tenter in range(self.n_intervals):
            for tstart in range(tenter - self.pre_intervals, tenter + 1):
                if tenter - tstart > self.pre_intervals:
                    continue
                self.mats[tenter][tstart] = MatrixAss.OD(self.origins, self.destinations, self.detectors)

    def from_pandas(self, df: pd.DataFrame) -> MatrixAss:
        dict_df = df.to_dict(orient="records")
        for r in dict_df:
            tenter, tstart = r["tenter"], r["tstart"]
            if tenter in self.mats and tstart in self.mats[tenter]:
                od: MatrixAss.OD = self.mats[tenter][tstart]
                od.mat[r["link"], r["od"]] += r["value"]
        return self

    def to_pandas(self) -> pd.DataFrame:
        records = []
        for tenter, tenter_dict in self.mats.items():
            for tstart, od in tenter_dict.items():
                mat = od.mat
                if mat.shape is None:
                    continue
                n_mat = mat.shape[0]
                for r in range(n_mat):
                    for ind in range(mat.indptr[r], mat.indptr[r + 1]):
                        o, d = od.get_origin_destination(mat.indices[ind])
                        records.append(
                            {
                                "tenter": tenter,
                                "tstart": tstart,
                                "link": r,
                                "origin": o,
                                "destination": d,
                                "od_index": od.mat.indices[ind],
                                "value": od.mat.data[ind],
                            }
                        )
        return pd.DataFrame(records)

    def write(self, params: OutputParameters | dict[str, Any]):
        params = OutputParameters.parse(params)
        params = copy.deepcopy(params)
        df = self.to_pandas()
        BaseLoader.write(engine=self.engine, df=df, params=params)

    def add(self, o, d, l, t_start, t_enter, flow):
        if l not in self.detectors:
            return
        # print(tstart,tenter)
        mat = self.mats.get(t_start, {}).get(t_enter)
        if mat is not None:
            io = self.o2i[o]
            id = self.d2i[d]
            il = self.l2i[l]
            mat.mat[io, id, il] += flow

    def __getitem__(self, key: tuple[int, int] | int) -> MatrixAss.OD:
        """
        Get the Matrix associated with the given key.

        Args:
            key (tuple): A tuple of (t_start, t_enter) representing the time intervals.

        Returns:
            MatrixAss.OD: The Matrix corresponding to the given key.

        Raises:
            KeyError: If the key is not found in the matrices.
        """
        tstart: int
        tenter: int
        if isinstance(key, tuple):
            tstart, tenter = key
            ret: MatrixAss.OD | None = self.mats.get(tstart, {}).get(tenter)
            if ret is not None:
                return ret
            else:
                od = MatrixAss.OD(self.origins, self.destinations, self.detectors)
                self.mats.setdefault(tstart, {})[tenter] = od
                return od
        else:
            raise KeyError(f"Key {key} not found in MatrixAss")

    def get_by_tstart(self, t_start: int) -> Generator[tuple[tuple[int, int], MatrixAss.OD], None, None]:
        """
        Args:
            t_start (int): The start time interval.

        Yields:
            tuple[tuple[int, int], MatrixAss.OD]: A tuple containing the (t_start, t_enter) key and the corresponding Matrix.
        """
        for t_enter, mat in self.mats.get(t_start, {}).items():
            yield ((t_enter, t_start), mat)

    def get_by_tenter(self, t_enter: int) -> Generator[tuple[tuple[int, int], MatrixAss.OD], None, None]:
        for t_start, mats_by_tenter in self.mats.items():
            if t_enter in mats_by_tenter:
                yield ((t_enter, t_start), mats_by_tenter[t_enter])
