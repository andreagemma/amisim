"""Container of the multimodal paths produced by the algorithms."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Generator

import pandas as pd
from graph import KPathList as PathsType
from graph import MultimodalPaths as MultimodalPathsType
from graph import Path as PathType
from graph import PathContainer

from ..base.base_loader import InputParameters, InputType, OutputParameters, OutputType
from ..base.base_model import BaseModel
from ..loaders.paths_loader import PathsLoader
from ..utils.time import get_intersecting_intervals
from .graph_model import GraphBase, GraphModel
from .modes_model import ModeCode
from .slice import Slice

__all__ = ["PathsModel", "PathsType", "MultimodalPathsType", "PathType"]


class PathsModel(BaseModel):
    """Hold the paths of each mode and read/write them through the loaders."""

    def __init__(
        self, modes: list[ModeCode] | None = None, paths: MultimodalPathsType | PathContainer | PathType | None = None
    ):
        """Store the paths, defaulting to an empty mapping."""
        super().__init__()
        self._paths = MultimodalPathsType()
        if paths is not None:
            if isinstance(paths, MultimodalPathsType):
                self._paths = paths
            else:
                self._paths.merge(paths)
        if modes is not None:
            for mode in modes:
                if mode not in self._paths:
                    self._paths[mode] = PathsType()

    @property
    def modes(self) -> list[str]:
        """Return the list of mode IDs."""
        return list(self._paths.modes)

    @property
    def paths(self) -> MultimodalPathsType:
        """Paths.

        Returns:
            A dictionary where the keys are mode IDs and the values are lists of paths.

        """
        return self._paths

    def __getitem__(self, key: str) -> PathsType:
        """Return the paths of the given mode."""
        if key not in self._paths:
            raise KeyError(f"Path with key '{key}' not found.")
        return self._paths[key]

    def __setitem__(self, key: str, value: PathsType) -> None:
        """Set the paths of the given mode."""
        self._paths[key] = value

    def n_paths(self) -> int:
        """Return the total number of paths across all modes."""
        return self._paths.n_paths()

    def n_unique_paths(self) -> int:
        """Return the total number of unique paths across all modes."""
        return self._paths.n_unique_paths()

    def k_paths(self) -> int:
        """Return the total number of k-paths across all modes."""
        return self._paths.k_paths()

    __len__ = n_paths

    def all_paths(self) -> Generator[PathType, None, None]:
        for mode in self._paths:
            for path in self._paths[mode].all_paths():
                yield path

    def all_kpaths(self, modes: list[str] | None = None) -> Generator[PathType, None, None]:
        for mode in modes or self._paths.modes:
            paths = self._paths.get(mode)
            if paths:
                yield from paths.all_kpaths()

    @classmethod
    def read(cls, kw_paths: InputType | None) -> PathsModel:
        """Read.

        Args:
            kw_paths: The parameters for reading the paths.

        Returns:
            An instance of `Paths` containing the read paths.

        """
        this = cls()
        if not bool(kw_paths):
            this.log.warning("No paths source provided.")
            return this
        kw_paths = InputParameters.parse(kw_paths)

        ret = PathsLoader.read(this.engine, params=kw_paths)
        if ret.df is not None:
            return cls.from_pandas(ret.df)
        else:
            raise ValueError("Failed to read paths")

    def write(self, graph: GraphModel | GraphBase, params: OutputType | dict[str, Any] | None = None) -> None:
        """Write the paths of every mode to the configured output.

        Args:
            graph: Graph providing the link geometries.
            params: Output parameters, already parsed or as a dictionary.
        """
        if params is None:
            params = self.parser.get(self.ini.PARAMS.PATHS_OUTPUT)
        if not bool(params):
            self.log.warning("No paths destination provided.")

        params = OutputParameters.parse(params)
        params = copy.deepcopy(params)

        if isinstance(graph, GraphModel):
            graph = graph.graph

        df = self.to_pandas(graph=graph, crs_source=params.crs_source)
        if df is not None:
            PathsLoader.write(engine=self.engine, df=df, params=params)

    @classmethod
    def read_state(cls, folder: Path | str, slice: Slice) -> MultimodalPathsType:
        """Read.

        Args:
            folder: The folder containing the path files for reading the paths.
            slice: The time slice for which to read the paths.

        Returns:
            An instance of `Paths` containing the read paths.

        """
        if cls.static_log is None or cls.static_app is None:
            cls()
        if cls.static_log is None or cls.static_app is None:
            raise RuntimeError("Failed to initialize static log and app.")
        if not bool(folder):
            raise ValueError("No folder provided for reading the graph.")
        if not isinstance(folder, (str, Path)):
            raise ValueError("Invalid folder type provided.")
        if slice.time_slice - slice.pre_load >= cls.static_app.ini.ASSIGNMENT.MAX_TIMESLICE:
            raise ValueError(
                f"Time slice cannot be greater than {cls.static_app.ini.ASSIGNMENT.MAX_TIMESLICE} minutes (current selection: {slice.time_slice})."
            )
        folder = Path(folder)
        folder /= cls.static_app.ini.PARAMS.STATE_PATHS
        this: MultimodalPathsType | None = None
        slice_work = slice
        offset = 0
        first_base: int | None = None
        while True:
            day_type = slice_work.start.day_type
            time_start = slice_work.start.minutes_from_midnight()
            time_end = slice_work.end.minutes_from_midnight(slice_work.start)
            day_type_folder = folder / f"day_type={day_type}"
            t_folders = list(f.stem.replace("t=", "") for f in day_type_folder.glob("t=*") if f.is_dir())
            int_folders = sorted([int(f) for f in t_folders if f.isdigit()])
            int_folders = get_intersecting_intervals(int_folders, time_start, time_end)
            if not int_folders:
                raise ValueError(
                    f"No path folders found in the range {time_start} to {time_end} for day type {day_type}."
                )
            for t in int_folders:
                src = day_type_folder / f"t={t}"
                for file in src.glob(f"*{cls.static_app.ini.OUTPUT.STATE_EXT}"):
                    cls.static_log.debug(f"Loading paths from file: {file.relative_to(folder)}")
                    new_paths: MultimodalPathsType = cls.load(file)
                    if new_paths is None:
                        continue
                    if this is None:
                        first_base = t + offset
                        new_paths.cut_time_slice(rebase=t + offset, shift=False, inplace=True, offset=offset)
                        this = new_paths
                    else:
                        new_paths.cut_time_slice(rebase=first_base, shift=False, inplace=True, offset=offset)
                        this.merge(new_paths)

            if time_end > 1440:
                new_start = slice_work.start.add(days=1).replace(hour=0, minute=0, second=0, microsecond=0)
                new_end = slice_work.results_end
                slice_work = Slice(
                    simulation_date=new_start,
                    start=new_start,
                    end=new_end,
                    delta_t=slice_work.delta_t,
                    pre_load=0,
                )
                offset += 1440
            else:
                break
        if this is None:
            raise ValueError("No paths were loaded from the provided folder.")
        this.cut_time_slice(time_start=slice.time_start, time_end=slice.time_end)
        cls.static_log.debug(f"Loaded paths: {this.to_str()}")
        return this

    @classmethod
    def write_state(cls, paths: MultimodalPathsType, destination: Path | str, slice: Slice) -> None:
        """Write the current state of the paths to a file."""
        if cls.static_log is None or cls.static_app is None:
            cls()
        if cls.static_log is None or cls.static_app is None:
            raise RuntimeError("Failed to initialize static log and app.")
        if isinstance(destination, str):
            destination = Path(destination)
        t = slice.results_start_time % 1440
        day_type = slice.results_start.day_type
        destination = Path(destination) / cls.static_app.ini.PARAMS.STATE_PATHS / f"day_type={day_type}" / f"t={t}"
        destination.mkdir(parents=True, exist_ok=True)
        for path in paths.all_paths():
            path["t_base"] %= 1440
            path["t"] = path["t_base"] + path["t_start"]
        cls.dump(paths, destination / f"paths{cls.static_app.ini.OUTPUT.STATE_EXT}")

    def merge(self, other: PathsModel | MultimodalPathsType) -> PathsModel:
        """Merge another PathsModel into this one."""
        if isinstance(other, PathsModel):
            other = other._paths
        if not isinstance(other, MultimodalPathsType):
            raise ValueError("Can only merge with another PathsModel or MultimodalPathsType instance.")
        self._paths.merge(other)
        return self

    def to_pandas(
        self, graph: GraphModel | GraphBase, crs_source: str | dict[str, str] | None = None
    ) -> pd.DataFrame | None:
        """Convert all paths to a pandas DataFrame."""
        if isinstance(graph, GraphModel):
            graph = graph.graph

        crs: str
        if isinstance(crs_source, dict):
            crs = crs_source.get("geometry", self.ini.GENERAL.CRS)
        else:
            crs = crs_source or self.ini.GENERAL.CRS
        return self._paths.to_pandas(G=graph, crs_link=crs)

    @classmethod
    def from_pandas(cls, df: pd.DataFrame) -> PathsModel:
        """Build a `Paths` instance grouping the dataframe rows by mode.

        Args:
            df: Dataframe with a `mode` column and the path columns.

        Returns:
            The paths grouped by mode.
        """
        this = cls()
        this._paths = MultimodalPathsType()
        if df is None or df.empty:
            pass
        else:
            for mode, df in df.groupby("mode"):
                this._paths[mode] = PathsType.from_pandas(df)
        return this

    @classmethod
    def from_dict(cls, paths_dict: dict[str, PathsType]) -> PathsModel:
        """Build a `Paths` instance wrapping an existing mode-to-paths mapping.

        Args:
            paths_dict: Mapping from mode to its path list.

        Returns:
            The wrapped paths.
        """
        this = cls()
        this._paths = MultimodalPathsType()
        for mode, paths in paths_dict.items():
            this._paths.set_by_mode(mode, paths)  # type: ignore
        return this

    def __str__(self) -> str:
        """Return the number of paths per mode."""
        m_paths = {m: self.paths.get_by_mode(m) for m in self.modes}
        paths = ", ".join(f"{m}:{p.n_paths()}" for m, p in m_paths.items() if p is not None)
        return f"Paths({paths})"
