"""ADAPTADOR de persistencia sobre PostgreSQL.

Es la pieza que el escenario 1 reemplaza. Para migrar a otro motor se escribe
otra clase que implemente `RepositorioTrabajos` y se cambia la fábrica: cero
archivos tocados en `dominio/` y `aplicacion/`.
"""
from uuid import UUID

from gestion_trabajos.config.db import db

from ..dominio.entidades import Trabajo
from ..dominio.repositorios import RepositorioTrabajos
from . import dto as modelo
from .mapeadores import MapeadorTrabajo


class RepositorioTrabajosPostgres(RepositorioTrabajos):
    def __init__(self):
        self._mapeador = MapeadorTrabajo()

    @property
    def mapeador(self) -> MapeadorTrabajo:
        return self._mapeador

    def obtener_por_id(self, id) -> Trabajo:
        registro = db.session.query(modelo.Trabajo).filter_by(id=str(id)).one_or_none()
        if not registro:
            return None
        return self.mapeador.dto_a_entidad(registro)

    def obtener_todos(self) -> list[Trabajo]:
        return [
            self.mapeador.dto_a_entidad(r) for r in db.session.query(modelo.Trabajo).all()
        ]

    def obtener_por_estado(self, estado: str) -> list[Trabajo]:
        registros = db.session.query(modelo.Trabajo).filter_by(estado=estado).all()
        return [self.mapeador.dto_a_entidad(r) for r in registros]

    def agregar(self, trabajo: Trabajo):
        db.session.add(self.mapeador.entidad_a_dto(trabajo))

    def actualizar(self, trabajo: Trabajo):
        db.session.merge(self.mapeador.entidad_a_dto(trabajo))

    def eliminar(self, id: UUID):
        db.session.query(modelo.Trabajo).filter_by(id=str(id)).delete()
