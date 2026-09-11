"""Consulta ObtenerTrabajo — el lado de lectura del CQS.

Es síncrona a propósito. No muta estado y no publica eventos.
"""
from dataclasses import dataclass

from gestion_trabajos.seedwork.aplicacion.queries import (
    Query,
    QueryResultado,
    ejecutar_query,
)

from ...dominio.repositorios import RepositorioTrabajos
from ..mapeadores import MapeadorTrabajoDTOJson
from .base import TrabajoQueryBaseHandler


@dataclass
class ObtenerTrabajo(Query):
    id: str = ''


class ObtenerTrabajoHandler(TrabajoQueryBaseHandler):
    def handle(self, query: ObtenerTrabajo) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)
        trabajo = repositorio.obtener_por_id(query.id)
        if not trabajo:
            return QueryResultado(resultado=None)
        return QueryResultado(
            resultado=self.fabrica_trabajos.crear_objeto(trabajo, MapeadorTrabajoDTOJson())
        )


@ejecutar_query.register(ObtenerTrabajo)
def ejecutar_query_obtener_trabajo(query: ObtenerTrabajo):
    return ObtenerTrabajoHandler().handle(query)
