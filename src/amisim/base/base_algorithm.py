"""Common base class shared by the AMISim algorithms."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..database import Execution
from .base_class import BaseClass


class BaseAlgorithm(BaseClass):
    """Base class giving algorithms access to the application and its logger."""

    def __init__(
        self,
        execution: Execution | None = None,
        **kwargs,
    ):
        """Store the application instance and its logger.

        Args:
            app: Running AMISim application.
            **kwargs: Extra arguments forwarded to the parent class.
        """
        super().__init__(**kwargs)
        self.name = self.__class__.__name__
        lista = self.parser.setdefault("run", [])
        lista.append({"name": self.name, "cwd": Path.cwd().as_posix(), "initialized": datetime.now().isoformat()})
        self.parser.set("run", lista)
        self._execution: Execution | None = execution
        self.log.extra["execution_id"] = self._execution.id if self._execution is not None else ""
        self._log_execution: bool = True
        if self._log_execution:
            self._log_executor = self.log.getChild("DB")

    @property
    def execution(self) -> Execution | None:
        return self._execution

    def set_execution_start(self, message: str | None = None) -> None:
        if self._execution is not None:
            if message is None:
                message = f"Starting execution {self.name}"
            self._execution.set_progress(self._execution.id, 0, message)
            if self._log_execution:
                self._log_executor.debug(message)

    def set_execution_progress(self, progress: float, message: str | None = None) -> None:
        if self._execution is not None:
            if message is None:
                message = f"Execution {self.name} in progress {progress}%"
            message += f" ({progress}%)"
            self._execution.set_progress(execution_id=self._execution.id, progress=progress, message=message)
            if self._log_execution:
                self._log_executor.debug(message)

    def set_execution_success(self, message: str | None = None) -> None:
        if self._execution is not None:
            message = message if message is not None else f"Execution {self.name} succeeded"
            self._execution.set_progress(execution_id=self._execution.id, progress=100, message=message)
            self._execution.set_execution_success(execution_id=self._execution.id)
            if self._log_execution:
                self._log_executor.debug(message)

    def set_execution_failed(self, message: str | None, ex: Exception | None = None) -> None:
        if self._execution is not None:
            message = message if message is not None else f"Execution {self.name} failed"
            self._execution.set_progress(execution_id=self._execution.id, progress=100, message=message)
            self._execution.set_execution_failed(execution_id=self._execution.id, ex=ex)
            if self._log_execution:
                self._log_executor.error(message)
                if ex is not None:
                    self._log_executor.error(str(ex))

    def init(self, **kwargs) -> BaseAlgorithm:
        """Initialize the algorithm and return the instance."""
        return self

    def update(self, **kwargs) -> BaseAlgorithm:
        """Update the algorithm's parameters. Should be implemented by subclasses."""
        return self

    def run(self, **kwargs) -> BaseClass | None:
        """Run the algorithm. Should be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement the run method.")

    def close(self) -> None:
        """Finalize the algorithm run by setting the end time."""
        lista = self.parser.setdefault("run", [])
        for item in lista:
            if item.get("name") == self.name:
                item["closed"] = datetime.now().isoformat()
        self.parser.set("run", lista)

    def __enter__(self) -> BaseAlgorithm:
        """Enter the runtime context related to this object."""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the runtime context and close the algorithm."""
        self.close()

    def __del__(self):
        self.close()


__all__ = ["BaseAlgorithm"]
