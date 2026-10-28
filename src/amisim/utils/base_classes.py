"""Reusable base classes shared by the AMISim data structures."""

from collections.abc import Iterator, Mapping
from dataclasses import asdict, fields
from typing import Any, TypeVar, cast

TDictMixin = TypeVar("TDictMixin", bound="DictMixin")


class DictMixin:
    """Add dictionary conversion helpers to a dataclass."""

    @classmethod
    def from_dict(cls: type[TDictMixin], data: Mapping[str, Any]) -> TDictMixin:
        """From dict.

        Args:
            data: A mapping containing the data to initialize the instance.

        Returns:
            An instance of the class initialized with the provided data.

        """
        nomi_campi = {campo.name for campo in fields(cast(Any, cls)) if campo.init}

        campi_sconosciuti = set(data) - nomi_campi

        if campi_sconosciuti:
            raise ValueError(f"Campi non riconosciuti: {sorted(campi_sconosciuti)}")

        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        """To dict.

        Returns:
            A dictionary with the dataclass field names and values.

        """
        return asdict(cast(Any, self))

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        # Permette di scrivere dict(istanza)
        """Iterate over the `(field, value)` pairs of the instance.

        Returns:
            An iterator over the field name and value pairs.

        """
        yield from self.to_dict().items()
