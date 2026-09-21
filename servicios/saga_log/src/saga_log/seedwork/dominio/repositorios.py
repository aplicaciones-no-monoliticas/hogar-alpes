"""Puertos de salida del dominio. La infraestructura los implementa; el dominio
nunca importa una implementación concreta (inversión de dependencias)."""
from abc import ABC, abstractmethod
from uuid import UUID

from .entidades import Entidad


class Repositorio(ABC):
    @abstractmethod
    def obtener_por_id(self, id: UUID) -> Entidad:
        ...

    @abstractmethod
    def obtener_todos(self) -> list[Entidad]:
        ...

    @abstractmethod
    def agregar(self, entidad: Entidad):
        ...

    @abstractmethod
    def actualizar(self, entidad: Entidad):
        ...

    @abstractmethod
    def eliminar(self, id: UUID):
        ...


class Mapeador(ABC):
    """Traduce entre el modelo de dominio y una representación externa."""

    @abstractmethod
    def obtener_tipo(self) -> type:
        ...

    @abstractmethod
    def entidad_a_dto(self, entidad: Entidad):
        ...

    @abstractmethod
    def dto_a_entidad(self, dto) -> Entidad:
        ...
