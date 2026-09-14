"""Consulta ObtenerSeguimientoDeTrabajo — `GET /seguimientos/{trabajoId}`.
Reemplaza a `GET /trabajos/<id>/seguimiento` servido antes por GT leyendo el
módulo `operaciones` en el mismo proceso (G-6): ahora es la propia API de
Operaciones, sin llamadas síncronas entre servicios (RNF-1)."""
from dataclasses import dataclass

from operaciones.seedwork.aplicacion.queries import Query, QueryResultado, ejecutar_query

from ...dominio.repositorios import RepositorioSeguimientos
from .base import OperacionesQueryBaseHandler


@dataclass
class ObtenerSeguimientoDeTrabajo(Query):
    trabajo_id: str = ''


class ObtenerSeguimientoDeTrabajoHandler(OperacionesQueryBaseHandler):
    def handle(self, query: ObtenerSeguimientoDeTrabajo) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioSeguimientos)
        seguimiento = repositorio.obtener_por_trabajo(query.trabajo_id)
        if not seguimiento:
            return QueryResultado(resultado=None)
        return QueryResultado(
            resultado={
                'id': str(seguimiento.id),
                'trabajo_id': seguimiento.trabajo_id,
                'pais': seguimiento.pais,
                'canal': seguimiento.canal,
                'categoria': seguimiento.categoria,
                'estado_trabajo': seguimiento.estado_trabajo,
                'prioridad': seguimiento.ventana_sla.prioridad.value,
                'minutos_sla': seguimiento.ventana_sla.minutos,
                'fecha_creacion': seguimiento.fecha_creacion.isoformat(),
                'fecha_actualizacion': seguimiento.fecha_actualizacion.isoformat(),
            }
        )


@ejecutar_query.register(ObtenerSeguimientoDeTrabajo)
def ejecutar_query_obtener_seguimiento(query: ObtenerSeguimientoDeTrabajo):
    return ObtenerSeguimientoDeTrabajoHandler().handle(query)
