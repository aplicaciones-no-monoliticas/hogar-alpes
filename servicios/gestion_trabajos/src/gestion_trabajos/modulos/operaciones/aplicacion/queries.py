"""Consulta propia del módulo Operaciones (lado de lectura del CQS)."""
from dataclasses import dataclass

from gestion_trabajos.seedwork.aplicacion.queries import (
    Query,
    QueryResultado,
    QueryHandler,
    ejecutar_query,
)

from ..dominio.repositorios import RepositorioSeguimientos
from ..infraestructura.fabricas import FabricaRepositorioSeguimientos


@dataclass
class ObtenerSeguimientoDeTrabajo(Query):
    trabajo_id: str = ''


class ObtenerSeguimientoDeTrabajoHandler(QueryHandler):
    def handle(self, query: ObtenerSeguimientoDeTrabajo) -> QueryResultado:
        repositorio = FabricaRepositorioSeguimientos().crear_objeto(RepositorioSeguimientos)
        seguimiento = repositorio.obtener_por_trabajo(query.trabajo_id)
        if not seguimiento:
            return QueryResultado(resultado=None)
        return QueryResultado(
            resultado={
                'id': str(seguimiento.id),
                'trabajo_id': seguimiento.trabajo_id,
                'estado_trabajo': seguimiento.estado_trabajo,
                'prioridad': seguimiento.ventana_sla.prioridad.value,
                'minutos_sla': seguimiento.ventana_sla.minutos,
            }
        )


@ejecutar_query.register(ObtenerSeguimientoDeTrabajo)
def ejecutar_query_obtener_seguimiento(query: ObtenerSeguimientoDeTrabajo):
    return ObtenerSeguimientoDeTrabajoHandler().handle(query)
