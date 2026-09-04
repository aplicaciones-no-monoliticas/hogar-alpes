"""Implementación de la Unidad de Trabajo sobre la sesión de SQLAlchemy.

Se guarda en `flask.g`, de modo que todos los handlers que participan en un
mismo request comparten la misma transacción: el comando de `trabajos` y el
handler de `operaciones` hacen commit juntos o no hacen ninguno.
"""
from flask import g, has_app_context

from gestion_trabajos.config.db import db
from gestion_trabajos.seedwork.infraestructura.uow import UnidadDeTrabajo


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
        # Fuera del contexto Flask (consumidor de Pulsar en su propio hilo)
        if not hasattr(UnidadTrabajoSQLAlchemy, '_instancia'):
            UnidadTrabajoSQLAlchemy._instancia = UnidadTrabajoSQLAlchemy()
        return UnidadTrabajoSQLAlchemy._instancia

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
