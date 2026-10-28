from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast

import numpy as np

from .base_loader import BaseLoader, InputParameters, InputType, OutputParameters, OutputType

if TYPE_CHECKING:
    from ..amisim_app import AmisimApp
    from ..app_logger import AppLogger


class BaseClass:
    """Base class for all IO classes."""

    static_log: ClassVar[AppLogger | None] = None
    static_app: ClassVar[AmisimApp | None] = None

    def __init__(self):
        """Initialize the base IO class."""
        from ..amisim_app import AmisimApp
        from ..app_logger import AppLogger

        cls = self.__class__
        if cls.static_app is None:
            cls.static_app = AmisimApp.get_instance()
        if cls.static_log is None:
            cls.static_log = cast(AppLogger, cls.static_app.log.getChild(cls.__name__))

        self._app: AmisimApp = cls.static_app
        self._log: AppLogger = cls.static_log
        self.rng = np.random.default_rng(seed=42)

    def clone(self):
        return deepcopy(self)

    @property
    def app(self):
        return self._app

    @property
    def engine(self):
        return self._app.engine

    @property
    def ini(self):
        return self._app.ini

    @property
    def parser(self):
        return self._app.parser

    @property
    def parallel(self):
        return self._app.parallel

    @property
    def log(self):
        return self._log

    @property
    def workspace(self):
        return self._app.workspace

    @classmethod
    def load(cls, source: InputType, use_gataframe: bool = False, **kwargs) -> object:
        if source is None:
            raise ValueError("Source cannot be None")

        source = InputParameters.parse(source)
        if source is None:
            raise ValueError("Source cannot be None after parsing")

        if cls.static_app is None:
            cls()
        if cls.static_app is None:
            raise ValueError("Cannot initialize AmisimApp")
        app = cls.static_app
        if isinstance(source, list) or not isinstance(source.src, (str, Path)):
            use_gataframe = True
        if use_gataframe:
            return BaseLoader.read(app.engine, params=source)
        else:
            return app.serializer.load(source.src)  # type: ignore

    @classmethod
    def dump(
        cls, obj: object, destination: OutputType, mode="overwrite", use_gataframe: bool = False, **kwargs
    ) -> None:
        if destination is None:
            raise ValueError("Destination cannot be None")

        destination = OutputParameters.parse(destination)
        if destination is None:
            raise ValueError("Destination cannot be None for DataFrame")

        if cls.static_app is None:
            cls()
        if cls.static_app is None:
            raise ValueError("Cannot initialize AmisimApp")
        app = cls.static_app
        if not isinstance(destination.destination, (str, Path)):
            use_gataframe = True
        if use_gataframe:
            BaseLoader.write(app.engine, df=obj, params=destination, mode=mode)
        else:
            app.serializer.dump(obj, destination.destination)
