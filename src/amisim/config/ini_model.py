"""Runtime INI model with typed sections backed by ConfigReader."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, get_origin

from configreader import ConfigReader

from .._version import __app_name__

_LOG = logging.getLogger(f"{__app_name__}.ini_model")

__all__ = ["IniModel"]


class IniBase:
    """Base helper for runtime ConfigReader-backed INI access."""

    def __init__(self, settings_reader: ConfigReader, section: str | None = None) -> None:
        """Bind the helper to a settings reader and an optional INI section.

        Args:
            settings_reader: Reader providing the configuration values.
            section: Name of the INI section, or `None` for the root model.

        """
        self._settings_reader = settings_reader
        self._SECTION = section.upper() if section is not None else None
        self._FIELD_DEFAULTS: dict[str, Any] = {}
        self._FIELD_TYPES: dict[str, Any] = {}
        self._DYNAMIC_FIELDS: dict[str, str] = {}
        self._initialize_declared_fields()

    @staticmethod
    def _normalize_type_hint(type_hint: Any) -> Any:
        # Internal helper: normalize type hint.
        """Internal helper: normalize type hint."""
        if isinstance(type_hint, str):
            text = type_hint.lower()
            if "bool" in text:
                return bool
            if "int" in text:
                return int
            if "float" in text:
                return float
            if "dict" in text:
                return dict
            if "list" in text:
                return list
            if "str" in text:
                return str
            return Any
        origin = get_origin(type_hint)
        if origin is not None:
            return origin
        return type_hint

    def _initialize_declared_fields(self) -> None:
        # Internal helper: initialize declared fields.
        """Internal helper: initialize declared fields."""
        annotations = getattr(self.__class__, "__annotations__", {})
        for name, type_hint in annotations.items():
            if not name.isupper():
                continue
            self._FIELD_TYPES[name] = self._normalize_type_hint(type_hint)
            self._FIELD_DEFAULTS[name] = getattr(self.__class__, name, None)

    def register_dynamic_field(self, name: str, default_value: str) -> None:
        """Register dynamic field.

        Args:
            name: Name of the field, stored uppercase.
            default_value: Value returned when the field is not configured.

        """
        field = name.upper()
        self._DYNAMIC_FIELDS[field] = str(default_value)

    def has_field(self, name: str) -> bool:
        """Has field.

        Args:
            name: Name of the field to look up.

        Returns:
            `True` if the field is declared or registered dynamically.

        """
        field = name.upper()
        return field in self._FIELD_DEFAULTS or field in self._DYNAMIC_FIELDS

    def fields(self) -> list[str]:
        """Get all declared and dynamic fields.

        Returns:
            List of field names.

        """
        return list(self._FIELD_DEFAULTS.keys()) + list(self._DYNAMIC_FIELDS.keys())

    def _typed_get(self, section: str, name: str, expected_type: Any, default: Any) -> Any:
        # Internal helper: typed get.
        """Internal helper: typed get."""
        try:
            if expected_type is bool:
                return self._settings_reader.getboolean(name, section=section, default=default)
            if expected_type is int:
                return self._settings_reader.getint(name, section=section, default=default)
            if expected_type is float:
                return self._settings_reader.getfloat(name, section=section, default=default)
            if expected_type is dict:
                return self._settings_reader.getdict(name, section=section, default=default)
            if expected_type is list:
                return self._settings_reader.getlist(name, section=section, default=default)
            return self._settings_reader.get(name, section=section, default=default)
        except Exception:
            return self._settings_reader.get(name, section=section, default=default)

    def get(self, section: str, name: str | None = None, default: Any = None) -> Any:
        """Read values on-demand from ConfigReader.

        Root model usage:
            get("SECTION", "NAME", default=None)
        Section usage:
            get("NAME", default=None)
        """
        if self._SECTION is None:
            if name is None:
                raise ValueError("Root IniModel.get requires section and name")
            target_section = section.upper()
            target_name = name.upper()
            section_obj = getattr(self, target_section, None)
            expected_type = Any
            resolved_default = default
            if section_obj is not None and isinstance(section_obj, IniBase):
                expected_type = section_obj._FIELD_TYPES.get(target_name, str)
                if default is None:
                    resolved_default = section_obj._DYNAMIC_FIELDS.get(
                        target_name,
                        section_obj._FIELD_DEFAULTS.get(target_name),
                    )
            return self._typed_get(target_section, target_name, expected_type, resolved_default)

        target_section = self._SECTION
        target_name = section.upper()
        expected_type = self._FIELD_TYPES.get(target_name, str)
        resolved_default = default
        if default is None:
            resolved_default = self._DYNAMIC_FIELDS.get(target_name, self._FIELD_DEFAULTS.get(target_name))
        return self._typed_get(target_section, target_name, expected_type, resolved_default)

    def __getattribute__(self, name: str) -> Any:
        """Resolve uppercase attributes through the settings reader.

        Args:
            name: Attribute name being accessed.

        Returns:
            The configured value for INI fields, the plain attribute otherwise.

        """
        if name.isupper():
            section = object.__getattribute__(self, "_SECTION")
            if section is not None:
                field_defaults = object.__getattribute__(self, "_FIELD_DEFAULTS")
                dynamic_fields = object.__getattribute__(self, "_DYNAMIC_FIELDS")
                if name in field_defaults or name in dynamic_fields:
                    getter = object.__getattribute__(self, "get")
                    return getter(name)
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str) -> Any:
        """Resolve dynamically registered INI fields.

        Args:
            name: Attribute name being accessed.

        Returns:
            The configured value of the field.

        Raises:
            AttributeError: If the field does not exist.

        """
        if self._SECTION is not None and name.isupper() and self.has_field(name):
            return self.get(name)
        raise AttributeError(f"{self.__class__.__name__} has no attribute {name}")

    def _create_dynamic_section(self, section: str) -> IniBase:
        """Create a runtime section subclass for unknown sections."""
        # Internal helper: create dynamic section.
        section_name = section.upper()
        dynamic_cls = type(section_name, (IniBase,), {"__annotations__": {}, "__module__": __name__})
        _LOG.warning(
            "Unknown settings section detected: %s. Creating dynamic section at runtime.",
            section_name,
        )
        return dynamic_cls(self._settings_reader, section=section_name)


class IniModel(IniBase):
    """Typed INI model with known sections and dynamic section discovery."""

    class GENERAL(IniBase):
        """General settings: coordinate systems, timezones and debug flags."""

        SRC_COEFS: str = ""
        SRC_CONV_TBL: str = ""
        DEBUG: bool = False
        CRS: str = "EPSG:4326"
        CRS_CALC: str = "EPSG:6875"
        TZ_LOCAL: str = "Europe/Rome"
        TZ_CALC: str = "UTC"
        CHECK_INPUT: bool = False
        RANDOM_SEED: int = 42

    class OUTPUT(IniBase):
        """Settings of the simulation output destinations."""

        OUTPUT_AGG_INT: int = 15
        OUTPUT_STATE_COMPRESSION: str = "zstd"
        OUTPUT_STATE_COMPRESSION_LEVEL: int = 5
        OUTPUT_IND_RES: bool = True
        MONITORED_VEH: int = 30
        OUTPUT_CONG_LEVELS: list[float] = [0.0, 0.25, 0.5, 0.75, 1.0]
        STATE_EXT: str = ".pkl.gz"
        LOS_CRITICO: float = 0.25

    class WEB_SERVER(IniBase):
        """Settings of the embedded web server."""

        WEB_SERVER_HOST: str = "0.0.0.0"
        WEB_SERVER_PORT: int = 5000
        WEB_SERVER_DEBUG: bool = False

    class DATABASE(IniBase):
        """Connection settings of the internal database."""

        DATABASE_URL: str = "sqlite:///:memory:"
        DATABASE_SCHEMA: str | None = None

    class DATABASE_SETTINGS(IniBase):
        """Settings of the database-backed dynamic configuration."""

        DB_SETTINGS_USE: bool = False
        DB_SETTINGS_URL: str = "sqlite:///:memory:"
        DB_SETTINGS_TABLE_NAME: str = "settings"
        DB_SETTINGS_QUERY: str = "SELECT value FROM settings WHERE name = :name and section = :section"

    class LOGGING(IniBase):
        """Logging settings: levels, sinks and formatting."""

        LOG_USE: bool = True
        LOG_LEVEL: str = "DEBUG"
        LOG_ON_DATABASE: bool = True
        LOG_ON_CONSOLE: bool = True
        LOG_ON_FILE: bool = True
        LOG_FORMAT: str = (
            "%(asctime)s | %(levelname)s | %(name)s | %(last_elapsed).2f/%(elapsed).2fs | "
            "%(execution_id)s -> %(message)s"
        )
        LOG_DIR: str = "log"

    class IPC(IniBase):
        """Settings of the inter-process communication channel."""

        IPC_USE: bool = True
        IPC_BUCKET: str = __app_name__
        IPC_BACKEND: str = "local"
        IPC_HOST: str = "localhost"
        IPC_PORT: int = 16379
        IPC_DB: int = 0
        IPC_COMPRESSION: str = "lz4"
        IPC_COMPRESSION_LEVEL: int = 5

    class PARALLEL(IniBase):
        """Settings of the parallel execution runtime."""

        PARALLEL_USE: bool = True
        PARALLEL_NUMCPUS: float = -1
        PARALLEL_ENGINE: str = "ray"
        PARALLEL_CLUSTER_ADDRESS: str = "local"

    class SIMULATOR(IniBase):
        """Settings of the traffic simulator."""

        SIMU_STEP: int = 6
        CAR_LENGTH: int = 5
        MIN_SPEED: int = 4
        LT1: int = 0
        LT2: int = 0
        COEFFICENTS: dict[str, dict[str, float]] = {
            "Corsia": {"C": 0.8, "L": 0.9, "E": 0.3, "S": 0.9},
            "Pioggia": {"0": 0, "1": 0.1, "2": 0.2, "3": 0.3},
            "Vento": {"0": 0, "1": 0.05},
            "Nebbia": {"0": 0, "1": 0.3, "2": 0.4, "3": 0.45},
            "Neve": {"0": 0, "1": 0.25, "2": 0.35},
        }

    class ASSIGNMENT(IniBase):
        """Settings of the traffic assignment procedure."""

        NUM_CPUS: float = 0.5
        MSA_MAX_ITE: int = 3
        MSA_RGAP: float = 0.01
        MSA_K: int = 3
        MAX_TIMESLICE: int = 1440
        SPP_NUM_CPUS: float = 0.5
        MSA_K_BALANCING: int = -1
        DELTA_T: int = 15
        PRELOAD: int = 0
        POSTLOAD: int = 0

    class OD_ESIMATION(IniBase):
        """Settings of the origin-destination matrix estimation."""

        OD_ESTIMATION_WHISKERS: int = 60
        OD_ESTIMATION_MAX_ITE: int = 2
        OD_ESTIMATION_RGAP: float = 0.01
        OD_ESTIMATION_MSA_MAX_ITE: int = 3
        OD_ESTIMATION_MSA_K: int = 3
        OD_ESTIMATION_MSA_RGAP: float = 0.001
        OD_ESTIMATION_MSA_TIMESLICE: int = 60
        OD_ESTIMATION_USE_OBSERVED_PATHS: bool = True
        OD_ESTIMATION_GAMMA1: float = 0.0
        OD_ESTIMATION_GAMMA2: float = 1.0
        OD_ESTIMATION_GAMMA3: float = 1.0
        OD_ESTIMATION_ITESA: int = 100
        OD_ESTIMATION_LAMBDA_LB: float = 0.0
        OD_ESTIMATION_LAMBDA_UB: float = 0.05
        OD_ESTIMATION_EPS: float = 0.000001
        OD_ESTIMATION_EPS2: float = 10.0
        OD_ESTIMATION_SA: float = 0.362

    class FCD_SERVER(IniBase):
        """Connection settings of the floating car data server."""

        FCD_SERVER_MAP_MATCHING: bool = False
        FCD_SERVER_TRIPS: bool = False
        FCD_SERVER_ROUTING: bool = True
        FCD_SERVER_UPDATE_SPEED: bool = True
        FCD_SERVER_SAVE_DELAY: int = 0
        FCD_SERVER_SAVE_START: str | None = None
        FCD_SERVER_RECOVERY_MODE: bool = False
        FCD_SERVER_FCD_TIMESLICE: int = 5
        FCD_SERVER_FCD_TIMESLICE_OFFLINE: int = 120
        FCD_SERVER_FCD_HORIZON: int = 60
        FCD_SERVER_SHARE_DATA_ONLINE: bool = True
        FCD_SERVER_WRITE_OUTPUT: bool = True
        FCD_SERVER_WRITE_STATE: bool = True

    class FCD_SPEED(IniBase):
        """Settings of the speed computation from floating car data."""

        FCD_SPEED_AGGREGATION_INTERVAL: int = 60

    class FCD_MAP_MATCHING(IniBase):
        """Settings of the floating car data map matching."""

        FCD_MAP_MATCHING_CPUS: int = 0
        FCD_MAP_MATCHING_MAX_DISTANCE: int = 50
        FCD_MAP_MATCHING_MAX_ANGLE: int = 45

    class FCD_ROUTING(IniBase):
        """Settings of the routing applied to floating car data."""

        FCD_ROUTING_CPUS: int = 0
        FCD_ROUTING_START_FROM_ZONE: int = 1
        FCD_ROUTING_END_TO_ZONE: int = 1
        FCD_ROUTING_AGGRATION_INTERVAL: int = 15
        FCD_ROUTING_CLUSTERING: bool = True
        FCD_ROUTING_CLUSTERING_EPS: int = 100

    class FCD_TRIPS(IniBase):
        """Settings of the trip reconstruction from floating car data."""

        FCD_TRIPS_CPUS: int = 0
        FCD_TRIPS_SIGNAL_BREAK_MAX_DT: int = 900
        FCD_TRIPS_SIGNAL_BREAK_DT: int = 300
        FCD_TRIPS_SIGNAL_BREAK_V: float = 0.5555555555555556
        FCD_TRIPS_STOP_O_DS: int = 50
        FCD_TRIPS_STOP_D_DS: int = 50
        FCD_TRIPS_SIGNAL_CONT_DT: int = 600
        FCD_TRIPS_SIGNAL_CONT_V: float = 0.1388888888888889
        FCD_TRIPS_MAX_V3: float = 69.44444444444444
        FCD_TRIPS_MAX_DISTANCE_OVERRIDE_POSITION_FIRST_POINT: int = 200
        FCD_TRIPS_MIN_LENGTH: int = 100
        FCD_TRIPS_MIN_TIME: int = 1
        FCD_TRIPS_REMOVE_STOPS: bool = False
        FCD_TRIPS_MAX_DISTANCE_BETWEEN_DATA: int = 20000
        FCD_TRIPS_MAX_DELTA_PROGR: int = 20000

    class GRAPH(IniBase):
        """Settings of the graph construction and turn penalties."""

        GRAPH_ADD_TURN_PENALTIES: bool = True
        GRAPH_PENALTY_ANGLES: list[int] = [30, 60, 120, 150]
        GRAPH_PENALTY_RIGHT_SLIGHT: int = 1
        GRAPH_PENALTY_RIGHT_ELBOW: int = 1
        GRAPH_PENALTY_RIGHT_SHARP: int = 2
        GRAPH_PENALTY_LEFT_SLIGHT: int = 4
        GRAPH_PENALTY_LEFT_ELBOW: int = 5
        GRAPH_PENALTY_LEFT_SHARP: int = 6
        GRAPH_PENALTY_U: int = 7

    class PARAMS(IniBase):
        """Settings of the parameters section."""

        ALGORITHM_LOG: str = "params.algorithm_log"
        PARAMS_RESULTS: str = "params.params_results"
        SETTINGS_RESULTS: str = "params.settings_results"

        SIMULATION_DATE: str = "simulation_date"
        SIMULATION_START: str = "start"
        SIMULATION_END: str = "end"

        SUPPLY: str = "params.supply"
        SUPPLY_NODES: str = "params.supply.*.nodes"
        SUPPLY_LINKS: str = "params.supply.*.links"
        SUPPLY_TURNS: str = "params.supply.*.turns"
        MODES: str = "params.modes"
        DEMAND: str = "params.demand"
        DETECTORS: str = "params.detectors"
        TRAFFIC_LIGHTS: str = "params.traffic_lights"
        EVENTS: str = "params.events"
        LINKS_SETS: str = "params.links_sets"
        MONITORED_LINKS_SETS: str = "params.monitored_links_sets"

        PATHS_OUTPUT: str = "params.paths"
        FLOWS_OUTPUT: str = "params.aggregated_results"
        STATS_OUTPUT: str = "params.aggregated_results_stats"
        TRACE_OUTPUT: str = "params.trace_results"
        SIGNALIZED_OUTPUT: str = "params.signalized_results"

        STATE: str = "params.state"
        STATE_GRAPH: str = "graph"
        STATE_PATHS: str = "paths"

    def __init__(self, settings_reader: ConfigReader) -> None:
        """Build the model and initialize declared and dynamic sections.

        Args:
            settings_reader: Reader providing the configuration values.

        """
        super().__init__(settings_reader=settings_reader, section=None)
        self._SECTIONS: dict[str, IniBase] = {}
        self._initialize_declared_sections()
        self._initialize_dynamic_sections()

    @classmethod
    def from_config(cls, settings_reader: ConfigReader) -> IniModel:
        """From config.

        Args:
            settings_reader: Reader providing the configuration values.

        Returns:
            The INI model bound to the given reader.

        """
        return cls(settings_reader)

    def _initialize_declared_sections(self) -> None:
        # Internal helper: initialize declared sections.
        """Internal helper: initialize declared sections."""
        for name, value in self.__class__.__dict__.items():
            if not name.isupper():
                continue
            if not isinstance(value, type) or not issubclass(value, IniBase):
                continue
            section_obj = value(self._settings_reader, section=name)
            self._SECTIONS[name] = section_obj
            setattr(self, name, section_obj)

    def _initialize_dynamic_sections(self) -> None:
        # Internal helper: initialize dynamic sections.
        """Internal helper: initialize dynamic sections."""
        for section in self._settings_reader.sections():
            section_up = section.upper()
            if section_up not in self._SECTIONS:
                section_obj = self._create_dynamic_section(section_up)
                self._SECTIONS[section_up] = section_obj
                setattr(self, section_up, section_obj)

            section_obj = self._SECTIONS[section_up]
            for field in self._settings_reader.variables(section_up):
                field_up = field.upper()
                if section_obj.has_field(field_up):
                    continue
                section_obj.register_dynamic_field(field_up, "")
                _LOG.warning(
                    "Unknown settings field detected: %s.%s. Registering dynamic runtime field as string.",
                    section_up,
                    field_up,
                )

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Return all the apparent configuration as a dictionary."""
        ret: dict[str, dict[str, Any]] = {}
        for name, section_obj in self._SECTIONS.items():
            ret[name] = {field: section_obj.get(field) for field in section_obj.fields()}
        return ret

    def to_yaml(self) -> str:
        """Return all the apparent configuration as a YAML string."""
        import yaml

        return yaml.dump(self.to_dict())

    def to_json(self) -> str:
        """Return all the apparent configuration as a JSON string."""
        import json

        return json.dumps(self.to_dict())

    def to_dataframe(self):
        """Return all the apparent configuration as a pandas DataFrame."""
        import pandas as pd

        return pd.DataFrame.from_dict(self.to_dict(), orient="index")

    def save_yaml(self, file_path: str | Path) -> None:
        """Save all the apparent configuration as a YAML file."""
        if isinstance(file_path, Path):
            file_path = str(file_path)
        import yaml

        with open(file_path, "w") as f:
            yaml.dump(self.to_dict(), f)

    def save_json(self, file_path: str | Path) -> None:
        """Save all the apparent configuration as a JSON file."""
        if isinstance(file_path, Path):
            file_path = str(file_path)
        import json

        with open(file_path, "w") as f:
            json.dump(self.to_dict(), f)

    def save(self, file_path: str | Path) -> None:
        """Save all the apparent configuration as a YAML or JSON file based on the file extension."""
        if isinstance(file_path, Path):
            file_path = str(file_path)
        if file_path.lower().endswith(".yaml") or file_path.lower().endswith(".yml"):
            self.save_yaml(file_path)
        elif file_path.lower().endswith(".json"):
            self.save_json(file_path)
        elif file_path.lower().endswith(".ini"):
            with open(file_path, "w") as f:
                f.write(self.to_ini())
        else:
            raise ValueError("Unsupported file extension. Use .yaml, .yml, .json, or .ini.")

    def to_ini(self) -> str:
        """Return all the apparent configuration as an INI string."""
        from io import StringIO

        with StringIO() as s:
            for section, fields in self.to_dict().items():
                s.write(f"[{section}]\n")
                for k, v in fields.items():
                    s.write(f"{k} = {v}\n")
                s.write("\n")
            return s.getvalue()


__all__ = ["IniBase", "IniModel"]
