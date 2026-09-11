from abc import ABC, abstractmethod

from gestion_trabajos.seedwork.dominio.repositorios import Repositorio

from .entidades import SeguimientoOperativo


class RepositorioSeguimientos(Repositorio, ABC):
    @abstractmethod
    def obtener_por_trabajo(self, trabajo_id: str) -> SeguimientoOperativo:
        ...
