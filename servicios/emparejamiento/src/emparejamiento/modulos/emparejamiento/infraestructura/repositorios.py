"""ADAPTADORES CRUD sobre PostgreSQL, uno por puerto de dominio."""
from emparejamiento.config.db import db

from ..dominio.entidades import Emparejamiento
from ..dominio.repositorios import RepositorioEmparejamientos, RepositorioProveedoresCandidatos
from . import dto as modelo
from .mapeadores import MapeadorEmparejamiento


class RepositorioEmparejamientosPostgres(RepositorioEmparejamientos):
    def __init__(self):
        self._mapeador = MapeadorEmparejamiento()

    def obtener_por_trabajo(self, trabajo_id) -> Emparejamiento | None:
        registro = (
            db.session.query(modelo.Emparejamiento)
            .filter_by(trabajo_id=str(trabajo_id))
            .one_or_none()
        )
        return self._mapeador.dto_a_entidad(registro) if registro else None

    def agregar(self, emparejamiento: Emparejamiento):
        db.session.add(self._mapeador.entidad_a_dto(emparejamiento))


class RepositorioProveedoresCandidatosPostgres(RepositorioProveedoresCandidatos):
    def buscar(self, categoria: str, pais: str, ciudad: str) -> list[dict]:
        from datetime import date

        registros = (
            db.session.query(modelo.ProveedorCandidato)
            .filter_by(categoria=categoria, pais=pais, ciudad=ciudad, estado='ACREDITADA')
            .filter(modelo.ProveedorCandidato.vigente_hasta >= date.today().isoformat())
            .all()
        )
        return [
            {'proveedor_id': r.proveedor_id, 'nivel': r.nivel, 'vigente_hasta': r.vigente_hasta}
            for r in registros
        ]

    def upsert(self, proveedor_id: str, categoria: str, pais: str, ciudad: str,
               nivel: str, estado: str, vigente_hasta: str, version: int):
        registro = (
            db.session.query(modelo.ProveedorCandidato)
            .filter_by(proveedor_id=proveedor_id, categoria=categoria)
            .one_or_none()
        )
        if registro is None:
            db.session.add(modelo.ProveedorCandidato(
                proveedor_id=proveedor_id, categoria=categoria, pais=pais, ciudad=ciudad,
                nivel=nivel, estado=estado, vigente_hasta=vigente_hasta, version=version,
            ))
            return

        if version <= registro.version:
            # Tolerante al desorden (§5.3): un evento viejo llegado tarde no
            # pisa uno más nuevo que ya se aplicó.
            return

        registro.pais = pais
        registro.ciudad = ciudad
        registro.nivel = nivel
        registro.estado = estado
        registro.vigente_hasta = vigente_hasta
        registro.version = version
