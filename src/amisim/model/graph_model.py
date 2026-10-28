"""Time dependent network graph built from nodes, links and turns sources."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from geopandas import GeoDataFrame
from graph import ActionPolicy, Link, Node, TimeDependentLinkBasedShortestPath, Turn
from graph import Graph as GraphBase
from pandas import DataFrame

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from ..loaders.links_loader import LinksLoader
from ..loaders.nodes_loader import NodesLoader
from ..loaders.turns_loader import TurnsLoader
from ..utils.time import get_intersecting_intervals
from .modes_model import ModesModel
from .slice import Slice

__all__ = ["GraphModel", "ActionPolicy", "Turn", "Link", "Node", "GraphBase", "TimeDependentLinkBasedShortestPath"]


class GraphModel(BaseModel):
    """Wrap the routing graph and the dataframes it was built from."""

    def __init__(
        self,
        t0: int = 0,
        total_time: int = 60,
        delta_t: int = 15,
        default_v: float | int = 50,
        graph: GraphBase | None = None,
    ):
        super().__init__()
        """Create an empty time dependent graph.

        Args:
            t0: Start time of the first interval.
            total_time: Total duration covered by the time intervals.
            delta_t: Length of each time interval.
            default_v: Free-flow speed used when a link has no `v0`.

        """
        self._nodes: GeoDataFrame | None = None
        self._links: GeoDataFrame | None = None
        self._turns: DataFrame | None = None
        self._default_v: float | int = default_v

        if graph is not None:
            self.graph = graph
        else:
            t0 = int(t0)
            total_time = int(total_time)
            delta_t = int(delta_t)
            self.graph = GraphBase(t0=t0, total_time=total_time, delta_t=delta_t)

    @classmethod
    def from_graph(cls, graph: GraphBase, default_v: float | int = 50) -> GraphModel:
        """Create a GraphModel instance from an existing GraphBase instance.

        Args:
            graph: The existing graph to wrap.
            default_v: Free-flow speed used when a link has no `v0`.

        Returns:
            A new GraphModel instance wrapping the provided graph.

        """
        instance = cls(
            t0=graph.t0,
            total_time=graph.total_time,
            delta_t=graph.delta_t,
            default_v=default_v,
        )
        instance.graph = graph
        if "centroids" not in instance.graph:
            instance.graph["centroids"] = [n["idx"] for n in graph.get_all_nodes() if n.get("centroid")]
        return instance

    @property
    def t0(self) -> int:
        """Start time of the first interval."""
        return self.graph.get("t0") if self.graph is not None else 0

    @t0.setter
    def t0(self, value: int):
        self.graph["t0"] = value if self.graph is not None else None

    @property
    def total_time(self) -> int:
        """Total duration covered by the time intervals."""
        return self.graph.get("total_time") if self.graph is not None else 0

    @property
    def delta_t(self) -> int:
        """Length of each time interval."""
        return self.graph.get("delta_t") if self.graph is not None else 0

    def resize_attributes(self, new_t0: int, new_total_time: int, new_delta_t: int):
        self.graph["t0"] = new_t0
        if self.graph is not None:
            self.graph.resize_attributes(new_total_time=new_total_time, new_delta_t=new_delta_t)

    def copy(self, copy_data: bool = True, copy_graph: bool = True) -> GraphModel:
        """Create a copy of the graph."""
        new_graph = GraphModel(
            t0=self.graph["t0"],
            total_time=self.graph["total_time"],
            delta_t=self.graph["delta_t"],
            default_v=self._default_v,
        )
        if copy_data:
            new_graph._nodes = self._nodes.copy() if self._nodes is not None else None
            new_graph._links = self._links.copy() if self._links is not None else None
            new_graph._turns = self._turns.copy() if self._turns is not None else None
        if copy_graph:
            new_graph.graph = self.graph.copy()
        new_graph._default_v = self._default_v
        return new_graph

    @property
    def nodes(self) -> GeoDataFrame | None:
        """Nodes.

        Returns:
            The nodes geodataframe, or `None` if the graph was not read yet.

        """
        return self._nodes

    @property
    def links(self) -> GeoDataFrame | None:
        """Links.

        Returns:
            The links geodataframe, or `None` if the graph was not read yet.

        """
        return self._links

    @property
    def turns(self) -> DataFrame | None:
        """Turns.

        Returns:
            The turns dataframe, or `None` if the graph was not read yet.

        """
        return self._turns

    @property
    def centroids(self) -> list[int] | None:
        """Centroids.

        Returns:
            The identifiers of the centroid nodes, or `None` if not read yet.

        """
        return self.graph.get("centroids") if self.graph is not None else None

    @classmethod
    def read_from_lnt(
        cls,
        kw_nodes: InputType,
        kw_links: InputType,
        kw_turns: InputType,
        modes: ModesModel,
        t0: int,
        total_time: int,
        delta_t: int,
        default_v: float | int = 50,
    ) -> GraphModel:
        """Read.

        Args:
            engine: Engine used to read the sources.
            kw_nodes: Parameters describing the nodes source.
            kw_links: Parameters describing the links source.
            kw_turns: Parameters describing the turns source.
            modes: Modes used to resolve the `modes` attributes.
            t0: Start time of the first interval.
            total_time: Total duration covered by the time intervals.
            delta_t: Length of each time interval.
            default_v: Free-flow speed used when a link has no `v0`.

        Returns:
            The graph populated with nodes, links and turns.

        Raises:
            ValueError: If one of the sources cannot be read or has a wrong type.

        """

        this = cls(t0=t0, total_time=total_time, delta_t=delta_t, default_v=default_v)
        this.graph["modes"] = modes.modes
        if not bool(kw_links):
            raise ValueError("No links source provided.")
        no_turns = False
        if not bool(kw_nodes):
            raise ValueError("No nodes source provided.")
        if not bool(kw_turns):
            this.log.warning("No turns source provided.")
            no_turns = True

        ret = NodesLoader.read(this.engine, params=kw_nodes)
        if ret is not None and ret.df is not None:
            if not isinstance(ret.df, GeoDataFrame):
                raise ValueError("Nodes must be a GeoDataFrame")
            this._nodes = ret.df
        else:
            raise ValueError("Failed to read nodes")

        ret = LinksLoader.read(this.engine, params=kw_links)
        if ret is not None and ret.df is not None:
            if not isinstance(ret.df, GeoDataFrame):
                raise ValueError("Links must be a GeoDataFrame")
            this._links = ret.df
        else:
            raise ValueError("Failed to read links")

        if no_turns:
            this._turns = DataFrame()
        else:
            ret = TurnsLoader.read(this.engine, params=kw_turns)
            if ret is not None and ret.df is not None:
                this._turns = DataFrame(ret.df)
            else:
                raise ValueError("Failed to read turns")

        _centroids: list[int] = []
        for node in this._nodes.to_dict(orient="records"):
            _idx = node.pop("id")
            _centroid = node.pop("centroid", None)
            _modes = modes.parse(node.pop("modes", None))
            _geometry = node.pop("geometry", None)
            _extra_node_attrs = {str(k): v for k, v in node.items()}
            this.graph.add_node(
                on_existing=ActionPolicy.WARN,
                idx=_idx,
                centroid=_centroid,
                geometry=_geometry,
                modes=_modes,
                time=this.graph.create_array_attribute(float("inf") if _centroid else 0),
                **_extra_node_attrs,
            )
            if _centroid:
                _centroids.append(_idx)

        this.graph["centroids"] = _centroids
        for link in this._links.to_dict(orient="records"):
            _from_node = link.pop("from_node", None)
            _to_node = link.pop("to_node", None)
            _idx = link.pop("id", None)
            if _idx is None:
                _idx = str(_from_node) + "-" + str(_to_node)
            _modes = modes.parse(link.pop("modes", None))
            _v0 = link.pop("v0", None)
            if _v0 is None:
                _v0 = this._default_v
            _connector = link.pop("connector", None)
            _lanes = link.pop("lanes", None)
            _alpha = link.pop("alpha", None)
            _rcr = link.pop("rcr", None)
            _capacity = link.pop("capacity", None)
            _length = link.pop("length", None)
            _geometry = link.pop("geometry", None)
            _t0 = link.pop("t0", None)
            if _t0 is None:
                _t0 = _length / _v0
            _extra_link_attrs = {str(k): v for k, v in link.items()}
            _flows = {f"flow_{mode}": this.graph.create_array_attribute(0) for mode in modes.modes.keys()}
            this.graph.add_link(
                on_existing=ActionPolicy.REPLACE,
                on_missing_node=ActionPolicy.RAISE,
                idx=_idx,
                i=_from_node,
                j=_to_node,
                v0=_v0,
                connector=_connector,
                lanes=_lanes,
                alpha=_alpha,
                rcr=_rcr,
                capacity=_capacity,
                length=_length,
                geometry=_geometry,
                modes=_modes,
                t0=_t0,
                flow=this.graph.create_array_attribute(0),
                time=this.graph.create_array_attribute(_t0),
                **_flows,
                **_extra_link_attrs,
            )

        for turn in this._turns.to_dict(orient="records"):
            _from_link = turn.pop("from_link", None)
            _to_link = turn.pop("to_link", None)
            _from_node = turn.pop("from_node", None)
            _via_node = turn.pop("via_node", None)
            _to_node = turn.pop("to_node", None)
            if _from_link is None:
                if _from_node is not None and _via_node is not None:
                    if flink := this.graph.get_link_by_nodes(_from_node, _via_node):
                        _from_link = flink.idx
            if _to_link is None:
                if _via_node is not None and _to_node is not None:
                    if tlink := this.graph.get_link_by_nodes(_via_node, _to_node):
                        _to_link = tlink.idx
            _idx = turn.pop("id", None)
            if _idx is None:
                _idx = str(_from_link) + "-" + str(_to_link)
            _penalty = turn.pop("penalty", None)
            _modes = turn.pop("modes", None)
            _extra_turn_attrs = {str(k): v for k, v in turn.items()}
            this.graph.add_turn(
                on_existing=ActionPolicy.WARN,
                on_missing_link=ActionPolicy.IGNORE,
                idx=_idx,
                in_link=_from_link,
                out_link=_to_link,
                penalty=_penalty,
                modes=_modes,
                **_extra_turn_attrs,
            )
        return this

    @classmethod
    def read_state(cls, folder: Path | str, slice: Slice, **kwargs) -> GraphBase:
        """Read.

        Args:
            folder: The folder containing the path files for reading the paths.
            slice: The simulation slice for which to read the paths.

        Returns:
            An instance of `GraphBase` containing the read graph.

        """
        if cls.static_log is None or cls.static_app is None:
            cls()
        if cls.static_log is None or cls.static_app is None:
            raise RuntimeError("Failed to initialize static log and app.")
        if not bool(folder):
            raise ValueError("No folder provided for reading the graph.")
        if not isinstance(folder, (str, Path)):
            raise ValueError("Invalid folder type provided.")
        MAX_TIMESLICE = cls.static_app.ini.ASSIGNMENT.MAX_TIMESLICE
        if slice.time_slice >= MAX_TIMESLICE:
            raise ValueError(
                f"Time slice cannot be greater than {MAX_TIMESLICE} minutes (current selection: {slice.time_slice})."
            )
        folder = Path(folder)
        folder /= cls.static_app.ini.PARAMS.STATE_GRAPH
        this: GraphBase | None = None
        slice_work = slice
        offset = 0
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
                    f"No graph folders found in the range {time_start} to {time_end} for day type {day_type}."
                )
            for t in int_folders:
                src = day_type_folder / f"t={t}"
                for file in src.glob(f"*{cls.static_app.ini.OUTPUT.STATE_EXT}"):
                    cls.static_log.debug(f"Loading graph from file: {file.relative_to(folder)}")
                    new_graph: GraphBase = cls.load(file)
                    if new_graph is None:
                        continue

                    if this is None:
                        new_graph.cut_time_slice(rebase=t + offset)
                        this = new_graph
                    elif new_graph is not None:
                        new_graph.cut_time_slice(rebase=t + offset)
                        this.merge(new_graph, copy=False, inplace=True)

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
            raise ValueError("No graph was loaded from the provided folder.")
        this.cut_time_slice(time_start=slice.time_start, time_end=slice.time_end)
        cls.static_log.debug(f"Loaded graph: {this.to_str()}")
        return this

    @classmethod
    def write_state(cls, graph: GraphBase, destination: Path | str, slice: Slice) -> None:
        """Write the current state of the paths to a file."""
        if not isinstance(destination, (str, Path)):
            raise ValueError("Destination must be a string or Path.")
        if cls.static_log is None or cls.static_app is None:
            cls()
        if cls.static_log is None or cls.static_app is None:
            raise RuntimeError("Failed to initialize static log and app.")
        destination = Path(destination) / cls.static_app.ini.PARAMS.STATE_GRAPH
        destination.mkdir(parents=True, exist_ok=True)
        file = destination / f"day_type={slice.results_start.day_type}" / f"t={slice.results_start_time % 1440}"
        file.mkdir(parents=True, exist_ok=True)
        cls.dump(graph, file / f"graph{cls.static_app.ini.OUTPUT.STATE_EXT}")

    def read(self, modes: ModesModel, params, t0: int, total_time: int, delta_t: int):
        """Read params.

        Args:
            modes: Modes used to resolve the `modes` attributes.
            params: Mapping with the `nodes`, `links` and `turns` parameters.

        Returns:
            The graph populated with nodes, links and turns.

        Raises:
            ValueError: If one of the required parameters is missing.

        """

        key_order = ["nodes", "links", "turns"]
        for key in key_order:
            if key not in params:
                raise ValueError(f"Missing parameter for {key}")
        kw_nodes = params.get("nodes", {})
        kw_links = params.get("links", {})
        kw_turns = params.get("turns", {})
        return self.read_from_lnt(
            kw_nodes=kw_nodes,
            kw_links=kw_links,
            kw_turns=kw_turns,
            modes=modes,
            t0=t0,
            total_time=total_time,
            delta_t=delta_t,
        )

    def get_index_time(self, t: int, agg_int: int) -> int:
        """Return the time interval index containing the instant `t`."""
        return int((t - self.graph["t0"]) // self.graph["delta_t"])

    def get_timestamps(self) -> list[int]:
        """Return the start instant of each time interval."""
        return [int(self.graph["t0"] + i * self.graph["delta_t"]) for i in range(self.graph["num_intervals"])]

    def get_t_starts(self) -> list[int]:
        """Return the start instant of each time interval."""
        return [int(i * self.graph["delta_t"]) for i in range(self.graph["num_intervals"])]

    def __str__(self) -> str:
        """Return a summary of the graph size and time discretization."""
        n_nodes = len(self._nodes) if self._nodes is not None else 0
        n_links = len(self._links) if self._links is not None else 0
        n_turns = len(self._turns) if self._turns is not None else 0
        n_centroids = len(self.centroids) if self.centroids is not None else 0
        delta_t = self.graph.get("delta_t") if self.graph is not None else None
        t0 = self.graph.get("t0", None) if self.graph is not None else None
        total_time = self.graph.get("total_time", None) if self.graph is not None else None

        return f"Graph(t0={t0}, total_time={total_time}, delta_t={delta_t}, nodes={n_nodes}, links={n_links}, turns={n_turns}, centroids={n_centroids})"

    def to_pandas_nodes(self, geometry: str = "geometry", save_into: bool = True) -> gpd.GeoDataFrame:
        """Return the nodes as a pandas DataFrame."""
        if "nodes" not in self.graph:
            return gpd.GeoDataFrame()
        ret = pd.DataFrame.from_dict(self.graph["nodes"], orient="index")
        ret.rename(columns={"idx": "id"}, inplace=True)
        if geometry not in ret.columns:
            raise ValueError(f"Nodes GeoDataFrame does not contain '{geometry}' column.")
        gret = gpd.GeoDataFrame(ret, geometry=geometry, crs=self.ini.GENERAL.CRS_CALC)
        if save_into:
            self._nodes = gret
        return gret

    def to_pandas_links(self, geometry: str = "geometry", save_into: bool = True) -> gpd.GeoDataFrame:
        """Return the links as a pandas DataFrame."""
        ret = pd.DataFrame.from_dict(self.graph["links"], orient="index")
        ret.rename(columns={"idx": "id"}, inplace=True)
        if geometry not in ret.columns:
            raise ValueError(f"Links GeoDataFrame does not contain '{geometry}' column.")
        gret = gpd.GeoDataFrame(ret, geometry=geometry, crs=self.ini.GENERAL.CRS_CALC)
        if save_into:
            self._links = gret
        return gret

    def to_pandas_turns(self, save_into: bool = True) -> pd.DataFrame:
        """Return the turns as a pandas DataFrame."""
        ret = pd.DataFrame.from_dict(self.graph["turns"], orient="index")
        ret.rename(columns={"idx": "id", "in_link": "from_link", "out_link": "to_link"}, inplace=True)
        if save_into:
            self._turns = ret
        return ret
