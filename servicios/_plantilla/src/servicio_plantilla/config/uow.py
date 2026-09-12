"""Unidad de Trabajo sobre la sesión de SQLAlchemy.

Dentro de una petición HTTP vive en `flask.g`, así que todos los handlers que
participan en la misma transacción de negocio confirman juntos o no confirma
ninguno. En el proceso consumidor, que no tiene petición, se usa una instancia
por hilo.
"""
import threading

from flask import g, has_app_context

from .db import db
from ..seedwork.infraestructura.uow import UnidadDeTrabajo

_local = threading.local()


class UnidadTrabajoSQLAlchemy(UnidadDeTrabajo):
    def __init__(self):
        super().__init__()
        self._savepoints: list = list()

    @staticmethod
    def obtener() -> 'UnidadTrabajoSQLAlchemy':
        if has_app_context():
            if 'uow' not in g:
                g.uow = UnidadTrabajoSQLAlchemy()
            return g.uow
        # Fuera del contexto de Flask: el proceso consumidor, en su propio hilo.
        if not hasattr(_local, 'uow'):
            _local.uow = UnidadTrabajoSQLAlchemy()
        return _local.uow

    def savepoint(self):
        self._savepoints.append(db.session.begin_nested())

    def rollback(self):
        if self._savepoints:
            self._savepoints.pop().rollback()
        else:
            db.session.rollback()
        self._limpiar_batches()

    def _commit(self):
        db.session.commit()
        self._savepoints = list()
