"""Unidad de Trabajo (Fowler) — Tutorial 5, semana 4.

Mantiene la lista de operaciones afectadas por una transacción de negocio y las
ejecuta como un todo. Es también el punto donde se decide CUÁNDO se publica cada
tipo de evento:

  - eventos de DOMINIO      -> antes del commit, en proceso, entre módulos
  - eventos de INTEGRACIÓN  -> después del commit, al broker

El orden importa: un evento de integración afirma un hecho hacia afuera. Si se
publicara antes del commit y la transacción fallara, se habría anunciado algo
que nunca ocurrió.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from pydispatch import dispatcher


@dataclass
class Batch:
    operacion: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)


class UnidadDeTrabajo(ABC):
    def __init__(self):
        self.batches: list[Batch] = list()
        # Un handler que reacciona a un evento puede registrar su propio batch,
        # que a su vez dispara otra publicación. Sin este registro, el primer
        # evento se reenviaría en cada ronda y los módulos se llamarían en ciclo.
        self._eventos_despachados: set = set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.rollback()

    def _limpiar_batches(self):
        self.batches = list()
        self._eventos_despachados = set()

    def obtener_eventos(self) -> list:
        eventos = []
        for batch in self.batches:
            for arg in batch.args:
                if hasattr(arg, 'eventos'):
                    eventos.extend(arg.eventos)
        return eventos

    def _eventos_pendientes(self, sufijo: str) -> list:
        pendientes = []
        for evento in self.obtener_eventos():
            clave = (evento.id, sufijo)
            if clave in self._eventos_despachados:
                continue
            self._eventos_despachados.add(clave)
            pendientes.append(evento)
        return pendientes

    def publicar_eventos_dominio(self):
        """En proceso, ANTES del commit. Así es como se hablan los módulos."""
        for evento in self._eventos_pendientes('dominio'):
            dispatcher.send(signal=f'{type(evento).__name__}Dominio', evento=evento)

    def publicar_eventos_integracion(self):
        """Al broker, DESPUÉS del commit. Aquí sí el hecho ya es cierto."""
        for evento in self._eventos_pendientes('integracion'):
            dispatcher.send(signal=f'{type(evento).__name__}Integracion', evento=evento)

    def registrar_batch(self, operacion: Callable, *args, **kwargs):
        self.batches.append(Batch(operacion, args, kwargs))
        self.publicar_eventos_dominio()

    def commit(self):
        for batch in self.batches:
            batch.operacion(*batch.args, **batch.kwargs)
        self._commit()
        self.publicar_eventos_integracion()
        self._limpiar_batches()

    @abstractmethod
    def _commit(self):
        ...

    @abstractmethod
    def rollback(self):
        ...

    @abstractmethod
    def savepoint(self):
        ...


class UnidadTrabajoPuerto:
    """Puerto estático hacia la UoW del request en curso.

    Los handlers de comando lo usan sin saber qué implementación hay detrás; el
    binding concreto (SQLAlchemy sobre PostgreSQL) se resuelve en `config.uow`.
    """

    @staticmethod
    def _uow():
        from gestion_trabajos.config.uow import UnidadTrabajoSQLAlchemy
        return UnidadTrabajoSQLAlchemy.obtener()

    @staticmethod
    def savepoint():
        UnidadTrabajoPuerto._uow().savepoint()

    @staticmethod
    def commit():
        UnidadTrabajoPuerto._uow().commit()

    @staticmethod
    def rollback():
        UnidadTrabajoPuerto._uow().rollback()

    @staticmethod
    def registrar_batch(operacion: Callable, *args, **kwargs):
        UnidadTrabajoPuerto._uow().registrar_batch(operacion, *args, **kwargs)
