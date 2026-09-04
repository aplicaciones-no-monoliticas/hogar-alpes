"""Puerto de persistencia del módulo.

Es una interfaz, no una implementación. Cambiar de PostgreSQL a DynamoDB
(escenario 1) significa escribir otro adaptador en `infraestructura`: ni esta
firma ni nada en `dominio` o `aplicacion` se toca.
"""
from abc import ABC, abstractmethod
from uuid import UUID

from gestion_trabajos.seedwork.dominio.repositorios import Repositorio

from .entidades import Trabajo


class RepositorioTrabajos(Repositorio, ABC):
    @abstractmethod
    def obtener_por_id(self, id: UUID) -> Trabajo:
        ...

    @abstractmethod
    def obtener_por_estado(self, estado: str) -> list[Trabajo]:
        ...
