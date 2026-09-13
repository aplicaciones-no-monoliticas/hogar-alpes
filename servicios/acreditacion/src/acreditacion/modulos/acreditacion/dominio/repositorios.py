"""Puerto de persistencia — Event Sourcing.

Distinto de un repositorio CRUD: `agregar` no reemplaza filas, **añade** las
del historial que todavía no se han escrito (`entidad.eventos`, los que dejó
pendientes el último comando). `obtener_por_id` no lee un registro, reproduce
el log completo del agregado.
"""
from abc import ABC, abstractmethod
from uuid import UUID

from .entidades import Acreditacion


class RepositorioAcreditaciones(ABC):
    @abstractmethod
    def obtener_por_id(self, id: UUID | str) -> Acreditacion | None:
        ...

    @abstractmethod
    def agregar(self, acreditacion: Acreditacion):
        ...

    @abstractmethod
    def historial(self, id: UUID | str) -> list[dict]:
        """Los eventos crudos del agregado, en orden — la evidencia de que el
        Event Sourcing es consultable (CA de la especificación §9)."""
        ...
