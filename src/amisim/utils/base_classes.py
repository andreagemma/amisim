from collections.abc import Iterator, Mapping
from dataclasses import asdict, fields
from typing import Any, TypeVar, cast


TDictMixin = TypeVar("TDictMixin", bound="DictMixin")


class DictMixin:
    @classmethod
    def from_dict(cls: type[TDictMixin], data: Mapping[str, Any]) -> TDictMixin:
        nomi_campi = {campo.name for campo in fields(cast(Any, cls)) if campo.init}

        campi_sconosciuti = set(data) - nomi_campi

        if campi_sconosciuti:
            raise ValueError(f"Campi non riconosciuti: {sorted(campi_sconosciuti)}")

        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        return asdict(cast(Any, self))

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        # Permette di scrivere dict(istanza)
        yield from self.to_dict().items()
