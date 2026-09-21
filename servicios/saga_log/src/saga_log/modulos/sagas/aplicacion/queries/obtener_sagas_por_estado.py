"""Consulta ObtenerSagasPorEstado — `GET /sagas?estado=` (CA-1.13, FR-012).

`INCOMPLETA` es calculada (D9 de research.md): no está en la tabla, se deriva
comparando `iniciada_en` contra el umbral configurado sobre las filas
`EN_CURSO`/`COMPENSANDO`.
"""
from dataclasses import dataclass

from saga_log.config.umbral import umbral_incompleta_segundos
from saga_log.seedwork.aplicacion.queries import Query, QueryHandler, QueryResultado, ejecutar_query

from ...infraestructura.repositorios import RepositorioSagas

ESTADOS_PERSISTIDOS = {'EN_CURSO', 'COMPLETADA', 'COMPENSANDO', 'COMPENSADA'}


def _externo(transaccion) -> dict:
    return {
        'trabajo_id': transaccion.trabajo_id,
        'correlation_id': transaccion.correlation_id,
        'estado': transaccion.estado,
        'iniciada_en': transaccion.iniciada_en.isoformat(),
        'terminada_en': transaccion.terminada_en.isoformat() if transaccion.terminada_en else None,
    }


@dataclass
class ObtenerSagasPorEstado(Query):
    estado: str = ''


class ObtenerSagasPorEstadoHandler(QueryHandler):
    def handle(self, query: ObtenerSagasPorEstado) -> QueryResultado:
        repo = RepositorioSagas()
        if query.estado == 'INCOMPLETA':
            transacciones = repo.obtener_incompletas(umbral_incompleta_segundos())
        elif query.estado in ESTADOS_PERSISTIDOS:
            transacciones = repo.obtener_por_estado(query.estado)
        else:
            transacciones = []
        return QueryResultado(resultado=[_externo(t) for t in transacciones])


@ejecutar_query.register(ObtenerSagasPorEstado)
def ejecutar_query_obtener_sagas_por_estado(query: ObtenerSagasPorEstado):
    return ObtenerSagasPorEstadoHandler().handle(query)
