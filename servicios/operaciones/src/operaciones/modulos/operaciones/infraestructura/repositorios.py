"""ADAPTADORES CRUD sobre PostgreSQL."""
from datetime import datetime

from operaciones.config.db import db

from ..dominio.entidades import SeguimientoOperativo
from ..dominio.repositorios import RepositorioEventosProcesados, RepositorioSeguimientos
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

    def contar_desde(self, desde) -> int:
        return (
            db.session.query(modelo.Seguimiento)
            .filter(modelo.Seguimiento.fecha_creacion >= desde)
            .count()
        )

    def agregar(self, seguimiento: SeguimientoOperativo):
        db.session.add(self._mapeador.entidad_a_dto(seguimiento))

    def actualizar(self, seguimiento: SeguimientoOperativo):
        seguimiento.fecha_actualizacion = datetime.utcnow()
        db.session.merge(self._mapeador.entidad_a_dto(seguimiento))

    def eliminar(self, id):
        db.session.query(modelo.Seguimiento).filter_by(id=str(id)).delete()


class RepositorioEventosProcesadosPostgres(RepositorioEventosProcesados):
    def ya_procesado(self, evento_id: str) -> bool:
        return (
            db.session.query(modelo.EventoProcesado)
            .filter_by(evento_id=str(evento_id))
            .one_or_none()
            is not None
        )

    def registrar(self, evento_id: str, tipo: str, resultado: str):
        db.session.add(modelo.EventoProcesado(
            evento_id=str(evento_id), tipo=tipo, resultado=resultado, fecha=datetime.utcnow(),
        ))

    def contar_por_resultado(self, resultado: str) -> int:
        return (
            db.session.query(modelo.EventoProcesado)
            .filter_by(resultado=resultado)
            .count()
        )
