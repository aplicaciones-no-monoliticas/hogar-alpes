"""Consulta ObtenerAcreditacion — reconstruida desde el event store.

Es la evidencia de que el Event Sourcing es consultable, no solo escribible:
la respuesta HTTP no viene de una tabla de estado, viene de reproducir el log.
"""
from dataclasses import dataclass

from acreditacion.seedwork.aplicacion.queries import (
    Query,
    QueryResultado,
    ejecutar_query,
)

from ...dominio.repositorios import RepositorioAcreditaciones
from ...infraestructura.mapeadores import MapeadorAcreditacionExterno
from .base import AcreditacionQueryBaseHandler


@dataclass
class ObtenerAcreditacion(Query):
    id: str = ''


class ObtenerAcreditacionHandler(AcreditacionQueryBaseHandler):
    def handle(self, query: ObtenerAcreditacion) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioAcreditaciones)
        acreditacion = repositorio.obtener_por_id(query.id)
        if not acreditacion:
            return QueryResultado(resultado=None)
        return QueryResultado(
            resultado=MapeadorAcreditacionExterno().entidad_a_externo(acreditacion)
        )


@ejecutar_query.register(ObtenerAcreditacion)
def ejecutar_query_obtener_acreditacion(query: ObtenerAcreditacion):
    return ObtenerAcreditacionHandler().handle(query)
