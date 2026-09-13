"""Consulta ObtenerEmparejamiento — `GET /emparejamientos/{trabajoId}`."""
from dataclasses import dataclass

from emparejamiento.seedwork.aplicacion.queries import (
    Query,
    QueryResultado,
    ejecutar_query,
)

from ...dominio.repositorios import RepositorioEmparejamientos
from .base import EmparejamientoQueryBaseHandler


@dataclass
class ObtenerEmparejamiento(Query):
    trabajo_id: str = ''


class ObtenerEmparejamientoHandler(EmparejamientoQueryBaseHandler):
    def handle(self, query: ObtenerEmparejamiento) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioEmparejamientos)
        emparejamiento = repositorio.obtener_por_trabajo(query.trabajo_id)
        if not emparejamiento:
            return QueryResultado(resultado=None)
        return QueryResultado(resultado={
            'trabajo_id': str(emparejamiento.trabajo_id),
            'region': emparejamiento.region,
            'categoria': emparejamiento.criterio.categoria,
            'pais': emparejamiento.criterio.pais,
            'ciudad': emparejamiento.criterio.ciudad,
            'candidatos': [c.proveedor_id for c in emparejamiento.candidatos],
            'total': len(emparejamiento.candidatos),
        })


@ejecutar_query.register(ObtenerEmparejamiento)
def ejecutar_query_obtener_emparejamiento(query: ObtenerEmparejamiento):
    return ObtenerEmparejamientoHandler().handle(query)
