from abc import ABC, abstractmethod

from operaciones.seedwork.dominio.repositorios import Repositorio

from .entidades import SeguimientoOperativo


class RepositorioSeguimientos(Repositorio, ABC):
    @abstractmethod
    def obtener_por_trabajo(self, trabajo_id: str) -> SeguimientoOperativo:
        ...

    @abstractmethod
    def contar_desde(self, desde) -> int:
        """Conteo de seguimientos creados desde una fecha — instrumento de
        CA-6.4 (verificar que la creación es 100% tras drenar el backlog)."""
        ...


class RepositorioEventosProcesados(ABC):
    """Idempotencia del consumidor (OPS-3): registra cada `evento_id` recibido
    con su resultado — APLICADO, DUPLICADO o HUERFANO — para que un cambio de
    estado sin seguimiento no se descarte en silencio (CA-6.5, corrige G-2)."""

    @abstractmethod
    def ya_procesado(self, evento_id: str) -> bool:
        ...

    @abstractmethod
    def registrar(self, evento_id: str, tipo: str, resultado: str):
        ...

    @abstractmethod
    def contar_por_resultado(self, resultado: str) -> int:
        ...
