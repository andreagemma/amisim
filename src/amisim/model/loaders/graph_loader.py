from ..nodes import Nodes
from ..links import Links
from ..turns import Turns
from graph import Graph as GraphBase, ActionPolicy
from ..base_model import InputType
from pandas import DataFrame
from geopandas import GeoDataFrame
from gataframe import Engine


class GraphLoader:
    def __init__(self, t0: float | int = 0, total_time: float | int = 60, delta_t: float | int = 15):
        self.graph = GraphBase(t0=t0, total_time=total_time, delta_t=delta_t)
        self._nodes: GeoDataFrame | None = None
        self._links: GeoDataFrame | None = None
        self._turns: DataFrame | None = None
        self._centroids: list[int] | None = None

    @property
    def nodes(self) -> GeoDataFrame | None:
        return self._nodes

    @property
    def links(self) -> GeoDataFrame | None:
        return self._links

    @property
    def turns(self) -> DataFrame | None:
        return self._turns

    @property
    def centroids(self) -> list[int] | None:
        return self._centroids

    @classmethod
    def read(cls, engine: Engine, kw_nodes: InputType, kw_links: InputType, kw_turns: InputType,
             t0: float | int = 0, total_time: float | int = 60, delta_t: float | int = 15) -> "GraphLoader":
        this = cls(t0=t0, total_time=total_time, delta_t=delta_t)
        ret = Nodes.read(engine, params=kw_nodes)
        if ret is not None and ret.df is not None:
            if not isinstance(ret.df, GeoDataFrame):
                raise ValueError("Nodes must be a GeoDataFrame")
            this._nodes = ret.df
        else:
            raise ValueError("Failed to read nodes")
        
        ret = Links.read(engine, params=kw_links)
        if ret is not None and ret.df is not None:
            if not isinstance(ret.df, GeoDataFrame):
                raise ValueError("Links must be a GeoDataFrame")
            this._links = ret.df
        else:
            raise ValueError("Failed to read links")

        ret = Turns.read(engine, params=kw_turns)
        if ret is not None and ret.df is not None:
            this._turns = DataFrame(ret.df)
        else:
            raise ValueError("Failed to read turns")

        this._centroids = []
        for node in this._nodes.to_dict(orient="records"):
            idx = node.pop("id")
            centroid = node.pop("centroid", None)
            modes = node.pop("modes", None)
            geometry = node.pop("geometry", None)
            extra_node_attrs = {str(k): v for k, v in node.items()}
            this.graph.add_node(
                on_existing=ActionPolicy.WARN,
                idx=idx,
                centroid=centroid,
                geometry=geometry,
                modes=modes,
                **extra_node_attrs,
            )
            if centroid:
                this._centroids.append(idx)

        for link in this._links.to_dict(orient="records"):
            from_node = link.pop("from_node", None)
            to_node = link.pop("to_node", None)
            idx = link.pop("id", None)
            if idx is None:
                idx = str(from_node) + "-" + str(to_node)
            v0 = link.pop("v0", None)
            connector = link.pop("connector", None)
            lanes = link.pop("lanes", None)
            alpha = link.pop("alpha", None)
            rcr = link.pop("rcr", None)
            capacity = link.pop("capacity", None)
            length = link.pop("length", None)
            geometry = link.pop("geometry", None)
            t0 = link.pop("t0", None)
            extra_link_attrs = {str(k): v for k, v in link.items()}
            this.graph.add_link(
                on_existing=ActionPolicy.REPLACE,
                on_missing_node=ActionPolicy.RAISE,
                idx=idx,
                i=from_node,
                j=to_node,
                v0=this.graph.create_array_attribute(v0),
                connector=connector,
                lanes=lanes,
                alpha=alpha,
                rcr=rcr,
                capacity=capacity,
                length=length,
                geometry=geometry,
                t0=this.graph.create_array_attribute(t0),
                **extra_link_attrs,
            )

        for turn in this._turns.to_dict(orient="records"):
            from_link = turn.pop("from_link", None)
            to_link = turn.pop("to_link", None)
            from_node = turn.pop("from_node", None)
            via_node = turn.pop("via_node", None)
            to_node = turn.pop("to_node", None)
            if from_link is None:
                if from_node is not None and via_node is not None:
                    if flink := this.graph.get_link_by_nodes(from_node, via_node):
                        from_link = flink.idx
            if to_link is None:
                if via_node is not None and to_node is not None:
                    if tlink := this.graph.get_link_by_nodes(via_node, to_node):
                        to_link = tlink.idx
            idx = turn.pop("id", None)
            if idx is None:
                idx = str(from_link) + "-" + str(to_link)
            penalty = turn.pop("penalty", None)
            modes = turn.pop("modes", None)
            extra_turn_attrs = {str(k): v for k, v in turn.items()}
            this.graph.add_turn(
                on_existing=ActionPolicy.WARN,
                on_missing_link=ActionPolicy.IGNORE,
                idx=idx,
                in_link=from_link,
                out_link=to_link,
                penalty=penalty,
                modes=modes,
                **extra_turn_attrs,
            )
        return this

    def read_params(self, engine: Engine, params):
        key_order = ["nodes", "links", "turns"]
        for key in key_order:
            if key not in params:
                raise ValueError(f"Missing parameter for {key}")
        kw_nodes = params.get("nodes", {})
        kw_links = params.get("links", {})
        kw_turns = params.get("turns", {})
        return self.read(engine, kw_nodes, kw_links, kw_turns)
