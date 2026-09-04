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
class ObtenerTrabajosPorEstado(Query):
    estado: str = ''


class ObtenerTrabajosPorEstadoHandler(TrabajoQueryBaseHandler):
    def handle(self, query: ObtenerTrabajosPorEstado) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)
        mapeador = MapeadorTrabajoDTOJson()
        trabajos = repositorio.obtener_por_estado(query.estado)
        return QueryResultado(
            resultado=[self.fabrica_trabajos.crear_objeto(t, mapeador) for t in trabajos]
        )


@ejecutar_query.register(ObtenerTrabajosPorEstado)
def ejecutar_query_obtener_por_estado(query: ObtenerTrabajosPorEstado):
    return ObtenerTrabajosPorEstadoHandler().handle(query)
