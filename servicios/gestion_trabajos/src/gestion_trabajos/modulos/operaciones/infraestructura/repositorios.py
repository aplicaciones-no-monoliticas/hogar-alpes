from gestion_trabajos.config.db import db

from ..dominio.entidades import SeguimientoOperativo
from ..dominio.repositorios import RepositorioSeguimientos
from . import dto as modelo
from .mapeadores import MapeadorSeguimiento


class RepositorioSeguimientosPostgres(RepositorioSeguimientos):
    def __init__(self):
        self._mapeador = MapeadorSeguimiento()

    def obtener_por_id(self, id) -> SeguimientoOperativo:
        registro = db.session.query(modelo.Seguimiento).filter_by(id=str(id)).one_or_none()
        return self._mapeador.dto_a_entidad(registro) if registro else None

    def obtener_por_trabajo(self, trabajo_id: str) -> SeguimientoOperativo:
        registro = (
            db.session.query(modelo.Seguimiento)
            .filter_by(trabajo_id=str(trabajo_id))
            .one_or_none()
        )
        return self._mapeador.dto_a_entidad(registro) if registro else None

    def obtener_todos(self) -> list[SeguimientoOperativo]:
        return [
            self._mapeador.dto_a_entidad(r)
            for r in db.session.query(modelo.Seguimiento).all()
        ]

    def agregar(self, seguimiento: SeguimientoOperativo):
        db.session.add(self._mapeador.entidad_a_dto(seguimiento))

    def actualizar(self, seguimiento: SeguimientoOperativo):
        db.session.merge(self._mapeador.entidad_a_dto(seguimiento))

    def eliminar(self, id):
        db.session.query(modelo.Seguimiento).filter_by(id=str(id)).delete()
