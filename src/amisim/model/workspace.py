from .loaders.graph_loader import GraphLoader
from .loaders.modes_loader import ModesLoader
from .loaders.matrix_loader import MatrixLoader
from typing import Any
from graph import Graph
from .modes import ModeType
from .base_model import InputType, InputParameters
from gataframe import Engine
from matrix import LabelsInput, Timestamp, MatrixODT


class Workspace:
    def __init__(self):
        self.graph: Graph | None = None
        self.centroids: list[int] = []
        self.modes: ModeType = None
        self.matrices: dict[str, MatrixODT] | None = None
        self.matrix_eq: MatrixODT | None = None

    def load_graph(
        self,
        engine: Engine,
        kw_nodes: InputType,
        kw_links: InputType,
        kw_turns: InputType,
        t0: float | int = 0,
        total_time: float | int = 60,
        delta_t: float | int = 15,
        force: bool = False,
    ):
        if self.graph is None or force:
            graph_loader = GraphLoader.read(
                engine=engine,
                kw_nodes=kw_nodes,
                kw_links=kw_links,
                kw_turns=kw_turns,
                t0=t0,
                total_time=total_time,
                delta_t=delta_t,
            )
            self.graph = graph_loader.graph
            self.centroids = graph_loader.centroids or []

    def load_modes(self, engine: Engine, kw_modes: InputType, force: bool = False):
        if self.graph is None:
            raise ValueError("Graph must be loaded before loading modes.")
        if self.modes is None or force:
            modes_loader = ModesLoader.read(engine=engine, kw_modes=kw_modes)
            self.modes = modes_loader.modes or {}

    def load_matrices(
        self,
        engine: Engine,
        modes: ModeType,
        centroids: LabelsInput,
        timestamps: list[Timestamp],
        kws_matrices: list[dict[str, InputType]],
        force: bool = False,
    ):
        if self.graph is None:
            raise ValueError("Graph must be loaded before loading matrices.")
        if self.matrices is None or force:
            matrix_loader = MatrixLoader.read(
                engine=engine, modes=modes, centroids=centroids, timestamps=timestamps, kws_matrices=kws_matrices
            )
            self.matrices = matrix_loader.matrices or {}
            self.matrix_eq = matrix_loader.matrix_eq or None
