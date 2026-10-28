"""Workspace holding the graph, modes, demand matrices and links sets."""

from datetime import datetime, timedelta
from typing import Any

from ..base.base_loader import InputType
from ..base.base_model import BaseModel
from .detectors_model import DetectorsModel
from .events_model import EventsModel
from .graph_model import GraphBase, GraphModel
from .links_sets_model import LinksSetsModel
from .matrices_model import MatricesModel, Timestamp
from .modes_model import ModesModel
from .monitored_links_sets_model import MonitoredLinksSetsModel
from .paths_model import MultimodalPathsType, PathsModel
from .simulation_interval import SimulationDatetime
from .slice import Slice
from .traffic_lights_model import TrafficLightsModel

__all__ = ["Workspace"]


class Workspace(BaseModel):
    """Load and keep the model objects shared by the algorithms."""

    def __init__(self):
        """Create an empty workspace bound to the given logger."""
        super().__init__()
        self._graph_model: GraphModel | None = None
        self._modes_model: ModesModel | None = None
        self._matrices_model: MatricesModel | None = None
        self._links_sets_model: LinksSetsModel | None = None
        self._detectors_model: DetectorsModel | None = None
        self._traffic_lights_model: TrafficLightsModel | None = None
        self.links_cost: str = "time"
        self.turns_cost: str = "time"
        self.nodes_cost: str = "time"
        self._simulation_slice: Slice | None = None
        self._events_model: EventsModel | None = None
        self._monitored_links_sets_model: MonitoredLinksSetsModel | None = None
        self._preloaded_paths_model: PathsModel | None = None

    @property
    def monitored_links_sets_model(self) -> MonitoredLinksSetsModel:
        if self._monitored_links_sets_model is None:
            self.load_monitored_links_sets()
        if self._monitored_links_sets_model is None:
            raise RuntimeError("Failed to load monitored links sets.")
        return self._monitored_links_sets_model

    def load_monitored_links_sets(
        self,
        kw_monitored_links_sets: InputType | None = None,
        force: bool = False,
    ) -> MonitoredLinksSetsModel:
        """Load monitored links sets.

        Args:
            kw_monitored_links_sets: Parameters describing the monitored links sets source.
            force: If `True`, reload the monitored links sets even if already loaded.

        Raises:
            ValueError: If the monitored links sets cannot be read.

        """
        self.log.debug("Starting to load monitored links sets.").tic()
        if self._monitored_links_sets_model is None or force:
            kw_monitored_links_sets = kw_monitored_links_sets or self.parser.get(self.ini.PARAMS.MONITORED_LINKS_SETS)
            if not bool(kw_monitored_links_sets) and not self.parser.has_key(self.ini.PARAMS.MONITORED_LINKS_SETS):
                self._monitored_links_sets_model = MonitoredLinksSetsModel()
                self.log.warning("Monitored links sets not found, initializing empty model.")
            else:
                self._monitored_links_sets_model = MonitoredLinksSetsModel.read(
                    kw_monitored_links_sets=kw_monitored_links_sets
                )
                if self._monitored_links_sets_model is None:
                    raise RuntimeError("Failed to read monitored links sets.")
                self.log.debug("Monitored links sets loaded successfully")
            self.log.debug("Monitored links sets loaded in %.2f seconds" % self.log.toc()).tic()
            self.log.debug(f"{self._monitored_links_sets_model}").tic()
        else:
            self.log.debug("Monitored links sets already loaded.")
        if self.graph_model is None or self.graph_model.graph is None:
            raise RuntimeError("Graph model not loaded.")
        self.graph_model.graph["monitored_links_sets"] = (
            self._monitored_links_sets_model.monitored_links_sets
            if self._monitored_links_sets_model is not None
            else {}
        )
        return self._monitored_links_sets_model

    @property
    def events_model(self) -> EventsModel:
        if self._events_model is None:
            self.load_events()
        if self._events_model is None:
            raise RuntimeError("Failed to load events.")
        return self._events_model

    def load_events(
        self,
        kw_events: InputType | None = None,
        force: bool = False,
    ) -> EventsModel:
        """Load events.

        Args:
            kw_events: Parameters describing the events source.
            force: If `True`, reload the events even if already loaded.

        Raises:
            RuntimeError: If the events cannot be read.

        """
        self.log.debug("Starting to load events...").tic()
        if self._events_model is None or force:
            kw_events = kw_events or self.parser.get(self.ini.PARAMS.EVENTS)
            if not bool(kw_events) and not self.parser.has_key(self.ini.PARAMS.EVENTS):
                self._events_model = EventsModel()
                self.log.warning("Events not found, initializing empty model.")
            else:
                self._events_model = EventsModel.read(kw_events=kw_events)
                if self._events_model is None:
                    raise RuntimeError("Failed to read events.")
                self.log.debug("Events loaded successfully")
            self.log.info("Events loaded in %.2f seconds" % self.log.toc()).tic()
            self.log.info(f"{self._events_model}").tic()
        else:
            self.log.debug("Events already loaded.")
        assert self._events_model is not None, "Events model not loaded."
        assert self._events_model.events is not None, "Events not loaded."
        self.graph_model.graph["events"] = self._events_model.events if self._events_model is not None else {}
        return self._events_model

    @property
    def traffic_lights_model(self) -> TrafficLightsModel:
        if self._traffic_lights_model is None:
            self.load_traffic_lights()
        if self._traffic_lights_model is None:
            raise RuntimeError("Failed to load traffic lights.")
        return self._traffic_lights_model

    def load_traffic_lights(
        self,
        kw_traffic_lights: InputType | None = None,
        force: bool = False,
    ) -> TrafficLightsModel:
        """Load traffic lights.

        Args:
            engine: Engine used to read the sources.
            kw_traffic_lights: Parameters describing the traffic lights source.
            force: If `True`, reload the traffic lights even if already loaded.

        Raises:
            RuntimeError: If the traffic lights cannot be read.

        """

        self.log.info("Starting to load traffic lights...").tic()
        if self._traffic_lights_model is None or force:
            kw_traffic_lights = kw_traffic_lights or self.parser.get(self.ini.PARAMS.TRAFFIC_LIGHTS)
            if not bool(kw_traffic_lights) and not self.parser.has_key(self.ini.PARAMS.TRAFFIC_LIGHTS):
                self._traffic_lights_model = TrafficLightsModel()
                self.log.warning("Traffic lights not found, initializing empty model.")
            else:
                self._traffic_lights_model = TrafficLightsModel.read(
                    kw_traffic_lights=kw_traffic_lights or self.parser.get(self.ini.PARAMS.TRAFFIC_LIGHTS)
                )
                if self._traffic_lights_model is None:
                    raise RuntimeError("Failed to read traffic lights.")
                self.log.debug("Traffic lights loaded successfully")
            self.log.info("Traffic lights loaded in %.2f seconds" % self.log.toc()).tic()
            self.log.info(f"{self._traffic_lights_model}").tic()
        else:
            self.log.debug("Traffic lights already loaded.")
        assert self._traffic_lights_model is not None, "Failed to load traffic lights."
        assert self._traffic_lights_model.traffic_lights is not None, "Traffic lights not loaded."
        self.graph_model.graph["traffic_lights"] = self._traffic_lights_model.traffic_lights
        return self._traffic_lights_model

    @property
    def simulation_slice(self) -> Slice:
        if self._simulation_slice is None:
            self.load_slice()
        if self._simulation_slice is None:
            raise RuntimeError("Failed to load simulation slice.")
        return self._simulation_slice

    def load_slice(
        self,
        time_start: int | str | datetime | None | SimulationDatetime = None,
        time_end: int | str | datetime | None | SimulationDatetime = None,
        date_simulation: str | datetime | None | SimulationDatetime = None,
        pre_load: int | None = None,
        post_load: int | None = None,
        delta_t: int | None = None,
        force: bool = False,
        **kwargs: Any,
    ) -> Slice:
        if self._simulation_slice is None or force:
            self.log.debug("Starting to load simulation slice...").tic()
            kwargs["force"] = force
            time_start = time_start or self.parser.get(self.ini.PARAMS.SIMULATION_START)
            time_end = time_end or self.parser.get(self.ini.PARAMS.SIMULATION_END)
            date_simulation = date_simulation or self.parser.get(self.ini.PARAMS.SIMULATION_DATE)
            pre_load = pre_load or self.ini.ASSIGNMENT.PRELOAD
            post_load = post_load or self.ini.ASSIGNMENT.POSTLOAD
            delta_t = delta_t or self.ini.ASSIGNMENT.DELTA_T
            simulation_date = SimulationDatetime(date_simulation, date_format="%Y-%m-%d").replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            start = SimulationDatetime(time_start, base_date=simulation_date)
            end = SimulationDatetime(time_end, base_date=simulation_date)
            while end < start:
                end = end.add(timedelta(days=1))
            self._simulation_slice = Slice(
                simulation_date=simulation_date,
                start=start.minutes_from_midnight(simulation_date.dt),
                end=end.minutes_from_midnight(simulation_date.dt),
                delta_t=delta_t,
                pre_load=pre_load,
                post_load=post_load,
            )
            self.log.info("Slices loaded in %.2f seconds" % self.log.toc()).tic()
            self.log.info(f"{self._simulation_slice}").tic()
        else:
            self.log.debug("Slice already loaded.")
        return self._simulation_slice

    @property
    def graph_model(self) -> GraphModel:
        if self._graph_model is None:
            self.load_graph()
        if self._graph_model is None:
            raise RuntimeError("Failed to load graph.")
        return self._graph_model

    def load_graph(
        self,
        kw_nodes: InputType | None = None,
        kw_links: InputType | None = None,
        kw_turns: InputType | None = None,
        force: bool = False,
    ) -> GraphModel:
        """Load graph.

        Args:
            engine: Engine used to read the sources.
            kw_nodes: Parameters describing the nodes source.
            kw_links: Parameters describing the links source.
            kw_turns: Parameters describing the turns source.
            slice: Slice object defining the time intervals.
            force: If `True`, reload the graph even if already loaded.

        Raises:
            RuntimeError: If modes are missing or the graph cannot be read.

        """
        self.log.debug("Starting to load graph...").tic()
        if self._modes_model is None:
            self.log.warning("Modes must be loaded before loading the graph. Default modes will be used if available.")
            self.load_modes()
            assert self._modes_model is not None, "Failed to load default modes."
        if self._simulation_slice is None:
            self.log.warning(
                "Simulation slice must be loaded before loading the graph. Default slice will be used if available."
            )
            self.load_slice()
            assert self._simulation_slice is not None, "Failed to load default simulation slice."
        if self._graph_model is None or force:
            kw_nodes_ex = kw_nodes or self.parser.get(self.ini.PARAMS.SUPPLY_NODES)
            kw_links_ex = kw_links or self.parser.get(self.ini.PARAMS.SUPPLY_LINKS)
            kw_turns_ex = kw_turns or self.parser.get(self.ini.PARAMS.SUPPLY_TURNS)
            self._graph_model = GraphModel.read_from_lnt(
                kw_nodes=kw_nodes_ex,
                kw_links=kw_links_ex,
                kw_turns=kw_turns_ex,
                modes=self._modes_model,
                t0=self._simulation_slice.time_start,
                total_time=self._simulation_slice.time_slice,
                delta_t=self._simulation_slice.delta_t,
            )
            if self._graph_model is None:
                raise RuntimeError("Failed to load graph.")
            self.log.info("Graph loaded in %.2f seconds" % self.log.toc()).tic()
            self.log.info(f"{self._graph_model}").tic()
        else:
            self.log.debug("Graph already loaded, skipping.")

        return self.graph_model

    @property
    def modes_model(self) -> ModesModel:
        if self._modes_model is None:
            self.load_modes()

        if self._modes_model is None:
            raise RuntimeError("Failed to load modes.")
        return self._modes_model

    def load_modes(self, kw_modes: InputType | None = None, force: bool = False) -> ModesModel:
        """Load modes.

        Args:
            kw_modes: Parameters describing the modes source.
            force: If `True`, reload the modes even if already loaded.

        Raises:
            RuntimeError: If the modes cannot be read.

        """
        self.log.debug("Starting to load modes...").tic()
        if self._modes_model is None or force:
            kw_modes = kw_modes or self.parser.get(self.ini.PARAMS.MODES)
            self._modes_model = ModesModel.read(kw_modes=kw_modes)
            if self._modes_model is None:
                raise RuntimeError("Failed to load modes.")
            self.log.info("Modes loaded in %.2f seconds" % self.log.toc()).tic()
            self.log.info(f"{self._modes_model}").tic()
        else:
            self.log.debug("Modes already loaded, skipping.")
        return self._modes_model

    @property
    def detectors_model(self) -> DetectorsModel:
        if self._detectors_model is None:
            self.load_detectors()
        if self._detectors_model is None:
            raise RuntimeError("Failed to load detectors.")
        return self._detectors_model

    def load_detectors(self, kw_detectors: InputType | None = None, force: bool = False) -> DetectorsModel:
        """Load detectors.

        Args:
            kw_detectors: Parameters describing the detectors source.
            force: If `True`, reload the detectors even if already loaded.

        Raises:
            RuntimeError: If the detectors cannot be read.

        """
        self.log.info("Starting to load detectors.").tic()
        if self._detectors_model is None or force:
            kw_detectors = kw_detectors or self.parser.get(self.ini.PARAMS.DETECTORS)
            if not bool(kw_detectors) and not self.parser.get(self.ini.PARAMS.DETECTORS):
                self._detectors_model = DetectorsModel()
                self.log.warning("Detectors not found, initializing empty model.")
            else:
                self._detectors_model = DetectorsModel.read(kw_detectors=kw_detectors)
                if self._detectors_model is None:
                    raise RuntimeError("Failed to load detectors.")
                self.log.info("Detectors loaded in %.2f seconds" % self.log.toc()).tic()
                self.log.info(f"{self._detectors_model}").tic()
        else:
            self.log.debug("Detectors already loaded, skipping.")
        assert self._graph_model is not None, "Graph must be loaded before accessing detectors."
        assert self._graph_model.graph is not None, (
            "Graph must have a valid graph structure before accessing detectors."
        )
        self.graph_model.graph["detectors"] = (
            self._detectors_model.detectors if self._detectors_model is not None else {}
        )
        return self._detectors_model

    @property
    def matrices_model(self) -> MatricesModel:
        if self._matrices_model is None:
            self.load_matrices()
        if self._matrices_model is None:
            raise RuntimeError("Failed to load matrices.")
        return self._matrices_model

    def load_matrices(
        self,
        timestamps: list[Timestamp] | None = None,
        kw_matrices: list[dict[str, InputType]] | None = None,
        slice: Slice | None = None,
        replace_timestamps: bool = False,
        force: bool = False,
    ) -> MatricesModel:
        """Load matrices.

        Args:
            engine: Engine used to read the matrices.
            timestamps: Time slices of the matrices.
            kw_matrices: One entry per mode with its matrices parameters.
            force: If `True`, reload the matrices even if already loaded.

        Raises:
            RuntimeError: If graph, modes or centroids are missing, or the
                matrices cannot be read.

        """
        self.log.debug("Starting to load matrices...").tic()
        if self._graph_model is None:
            self.log.warning("Graph must be loaded before loading matrices. Attempting to load default graph.")
            self.load_graph()
            if self._graph_model is None:
                raise RuntimeError("Graph must be loaded before loading matrices.")
        if self._modes_model is None:
            self.log.warning("Modes must be loaded before loading matrices. Attempting to load default modes.")
            self.load_modes()
            if self._modes_model is None:
                raise RuntimeError("Modes must be loaded before loading matrices.")
        if self._graph_model.centroids is None:
            self.log.warning(
                "Graph centroids must be available before loading matrices. Attempting to load default graph."
            )
            self.load_graph()
            if self._graph_model.centroids is None:
                raise RuntimeError("Graph centroids must be available before loading matrices.")
        if self._simulation_slice is None:
            if self._simulation_slice is None:
                self.log.warning(
                    "Simulation slice must be available before loading matrices. Attempting to load default slice."
                )
                self.load_slice()
            if self._simulation_slice is None:
                raise RuntimeError("Slice must be available before loading matrices.")

        if self._matrices_model is None or force:
            slice = slice or self._simulation_slice
            self._matrices_model = MatricesModel.read(
                centroids=self._graph_model.centroids,
                timestamps=timestamps or [x[0] for x in slice.intervals],
                kws_matrices=kw_matrices or self.parser.get(self.ini.PARAMS.DEMAND),
                slice=slice,
                replace_timestamps=replace_timestamps,
                modes=set(self._modes_model.codes),
            )
            if self._matrices_model is None:
                raise RuntimeError("Failed to load matrices.")
            self.log.info("Matrices loaded in %.2f seconds" % self.log.toc()).tic()
            self.log.info(f"{self._matrices_model} eq: {self._matrices_model.matrix_eq(self.modes_model).sum()}").tic()
        else:
            self.log.debug("Matrices already loaded, skipping.")
        return self._matrices_model

    @property
    def links_sets_model(self) -> LinksSetsModel:
        if self._links_sets_model is None:
            self.load_links_sets()
        if self._links_sets_model is None:
            raise RuntimeError("Failed to load links sets.")
        return self._links_sets_model

    def load_links_sets(
        self,
        kw_links_sets: InputType | None = None,
        force: bool = False,
    ) -> LinksSetsModel:
        """Load links sets.

        Args:
            engine: Engine used to read the links sets.
            kw_links_sets: Parameters describing the links sets source.
            force: If `True`, reload the links sets even if already loaded.

        Raises:
            RuntimeError: If the links sets cannot be read.

        """
        self.log.debug("Starting to load links sets...").tic()
        if self._links_sets_model is None or force:
            kw_links_sets = kw_links_sets or self.parser.get(self.ini.PARAMS.LINKS_SETS)
            if not bool(kw_links_sets) and not self.parser.get(self.ini.PARAMS.LINKS_SETS):
                self._links_sets_model = LinksSetsModel()
                self.log.warning("Links sets not found, initializing empty model.")
            else:
                self._links_sets_model = LinksSetsModel.read(
                    kw_links_sets=kw_links_sets or self.parser.get(self.ini.PARAMS.LINKS_SETS)
                )
                if self._links_sets_model is None:
                    raise RuntimeError("Failed to load links sets.")
            self.log.info("Links sets loaded in %.2f seconds" % self.log.toc()).tic()
            self.log.info(f"{self._links_sets_model}").tic()
        else:
            self.log.debug("Links sets already loaded, skipping.")
        assert self.graph_model is not None, "Graph must be loaded before accessing links sets."
        assert self.graph_model.graph is not None, (
            "Graph must have a valid graph structure before accessing links sets."
        )
        self.graph_model.graph["links_sets"] = (
            self._links_sets_model.links_sets if self._links_sets_model is not None else {}
        )
        return self._links_sets_model

    def load_preload_graph(self, slice: Slice | None = None, graph: GraphBase | None = None, force: bool = False):
        if self._graph_model is not None and not force:
            return self._graph_model
        try:
            self.log.debug("Starting to preload graph...").tic()
            if graph is None:
                graph = GraphModel.read_state(
                    folder=self.app.parser.get(self.ini.PARAMS.STATE), slice=slice or self.simulation_slice
                )
                if graph is None:
                    self.log.error("Graph state could not be read.")
            self._graph_model = GraphModel.from_graph(graph)
            if self._graph_model is None:
                self.log.error("Failed to preload graph, loading graph from scratch.")
                self.load_graph(force=True)
            else:
                self.log.info("Graph preloaded in %.2f seconds" % self.log.toc()).tic()
                self.log.info(f"{self._graph_model}").tic()
        except Exception as e:
            self.log.error(f"Failed to preload graph: {e}")
            self.load_graph(force=True)

    @property
    def has_preloaded_paths(self):
        return self._preloaded_paths_model is not None

    @property
    def preloaded_paths_model(self):
        if self._preloaded_paths_model is None:
            self.load_preload_paths()
        if self._preloaded_paths_model is None:
            raise RuntimeError("Failed to preload paths.")
        return self._preloaded_paths_model

    def load_preload_paths(
        self, slice: Slice | None = None, paths: MultimodalPathsType | None = None, force: bool = False
    ):
        try:
            if self._preloaded_paths_model is not None and not force:
                return self._preloaded_paths_model
            self.log.debug("Starting to preload paths...").tic()
            if paths is None:
                paths = PathsModel.read_state(
                    folder=self.app.parser.get(self.ini.PARAMS.STATE), slice=slice or self.simulation_slice
                )
                if paths is None:
                    self.log.error("Paths state could not be read.")
                    self._preloaded_paths_model = None
                else:
                    self._preloaded_paths_model = PathsModel(paths=paths)
                    self.log.info("Paths preloaded in %.2f seconds" % self.log.toc()).tic()
                    self.log.info(f"{self._preloaded_paths_model}").tic()
            else:
                self._preloaded_paths_model = PathsModel(paths=paths)
                self.log.info("Paths preloaded in %.2f seconds" % self.log.toc()).tic()
                self.log.info(f"{self._preloaded_paths_model}").tic()

            if self._preloaded_paths_model is None:
                self.log.error("Failed to preload paths, loading paths from scratch.")
        except Exception as e:
            self.log.error(f"Failed to preload paths: {e}")

    def auto_load(self, preload_graph: bool = False, preload_paths: bool = False, force: bool = False):
        tic = self.log.debug("Auto-loading workspace...").tic()

        self.load_slice(force=force)

        if self.simulation_slice is None:
            raise RuntimeError("Failed to load simulation slice.")

        self.load_modes(force=force)
        if self.modes_model is None:
            raise RuntimeError("Failed to load modes.")

        if preload_graph:
            self.load_preload_graph()
        else:
            self.load_graph(force=force)

        if self.graph_model is None:
            raise RuntimeError("Failed to load graph.")
        if not self.graph_model.centroids:
            raise RuntimeError("No centroids found in the graph.")

        self.load_matrices(force=force)

        if self.matrices_model is None:
            raise RuntimeError("Failed to load matrices.")

        self.log.tic()
        modes_ws = set(self.modes_model.codes)
        modes_mat = set(self.matrices_model.modes)
        modes_in_ws_no_mat = modes_ws - modes_mat
        modes_in_mat_no_ws = modes_mat - modes_ws
        if modes_ws != modes_mat:
            if len(modes_in_ws_no_mat) > 0:
                self.log.warning(
                    f"The modes {modes_in_ws_no_mat} in the workspace are not present in the matrices. Retaining only the matrix modes. {modes_ws & modes_mat} "
                )
                self.modes_model.retain(*self.matrices_model.modes)
            if len(modes_in_mat_no_ws) > 0:
                self.log.warning(
                    f"The modes {modes_in_mat_no_ws} in the matrices are not present in the workspace. Retaining only the workspace modes. {modes_ws & modes_mat} "
                )
                self.matrices_model.drop_modes(list(modes_in_mat_no_ws))

        modes_ws = set(self.modes_model.codes)
        modes_mat = set(self.matrices_model.modes)

        if len(modes_ws) == 0:
            raise RuntimeError("No modes loaded in the workspace.")
        if len(modes_mat) == 0:
            raise RuntimeError("No modes loaded in the matrices.")
        if modes_ws != modes_mat:
            raise RuntimeError("Mismatch between workspace modes and matrix modes.")

        self.log.info("Modes checked in %.2f seconds" % self.log.toc()).tic()

        if preload_paths:
            self.load_preload_paths()

        self.log.debug("Workspace auto-loaded in %.2f seconds" % tic.toc()).tic()

    def clear(self):
        self._simulation_slice = None
        self._modes_model = None
        self._graph_model = None
        self._matrices_model = None
        self._links_sets_model = None
        self._preloaded_paths_model = None
        self.log.info("Workspace cleared.")
