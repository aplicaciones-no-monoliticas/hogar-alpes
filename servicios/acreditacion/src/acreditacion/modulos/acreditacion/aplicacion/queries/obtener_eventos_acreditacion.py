"""Consulta ObtenerEventosAcreditacion — el historial completo.

`GET /acreditaciones/{id}/eventos`: la razón de ser del Event Sourcing en este
servicio (§4.4 de la especificación). Va directo al repositorio, sin pasar por
la reconstrucción del agregado: es infraestructura mostrando su propio log.
"""
from dataclasses import dataclass

from acreditacion.seedwork.aplicacion.queries import (
    Query,
    QueryResultado,
    ejecutar_query,
)

from ...dominio.repositorios import RepositorioAcreditaciones
from .base import AcreditacionQueryBaseHandler


@dataclass
class ObtenerEventosAcreditacion(Query):
    id: str = ''


class ObtenerEventosAcreditacionHandler(AcreditacionQueryBaseHandler):
    def handle(self, query: ObtenerEventosAcreditacion) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioAcreditaciones)
        return QueryResultado(resultado=repositorio.historial(query.id))


@ejecutar_query.register(ObtenerEventosAcreditacion)
def ejecutar_query_obtener_eventos_acreditacion(query: ObtenerEventosAcreditacion):
    return ObtenerEventosAcreditacionHandler().handle(query)
