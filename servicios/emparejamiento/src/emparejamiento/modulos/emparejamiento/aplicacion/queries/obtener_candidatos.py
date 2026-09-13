"""Consulta ObtenerCandidatos — `GET /candidatos?categoria=&pais=&ciudad=`, la
del escenario 8. Va directo a la proyección: sin llamadas síncronas a
Acreditación (RNF-1)."""
from dataclasses import dataclass

from emparejamiento.seedwork.aplicacion.queries import (
    Query,
    QueryResultado,
    ejecutar_query,
)

from ...dominio.repositorios import RepositorioProveedoresCandidatos
from .base import EmparejamientoQueryBaseHandler


@dataclass
class ObtenerCandidatos(Query):
    categoria: str = ''
    pais: str = ''
    ciudad: str = ''


class ObtenerCandidatosHandler(EmparejamientoQueryBaseHandler):
    def handle(self, query: ObtenerCandidatos) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioProveedoresCandidatos)
        return QueryResultado(
            resultado=repositorio.buscar(query.categoria, query.pais, query.ciudad)
        )


@ejecutar_query.register(ObtenerCandidatos)
def ejecutar_query_obtener_candidatos(query: ObtenerCandidatos):
    return ObtenerCandidatosHandler().handle(query)
