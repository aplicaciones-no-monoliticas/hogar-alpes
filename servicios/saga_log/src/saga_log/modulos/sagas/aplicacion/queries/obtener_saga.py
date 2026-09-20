"""Consulta ObtenerSaga — `GET /sagas/{trabajo_id}` (CA-1.12): estado y línea
de tiempo completa de una transacción, en orden cronológico.
"""
from dataclasses import dataclass

from saga_log.seedwork.aplicacion.queries import Query, QueryHandler, QueryResultado, ejecutar_query

from ...infraestructura.repositorios import RepositorioSagas


@dataclass
class ObtenerSaga(Query):
    trabajo_id: str = ''


class ObtenerSagaHandler(QueryHandler):
    def handle(self, query: ObtenerSaga) -> QueryResultado:
        repo = RepositorioSagas()
        transaccion = repo.obtener_transaccion(query.trabajo_id)
        if not transaccion:
            return QueryResultado(resultado=None)

        pasos = repo.obtener_pasos(query.trabajo_id)
        return QueryResultado(resultado={
            'trabajo_id': transaccion.trabajo_id,
            'correlation_id': transaccion.correlation_id,
            'estado': transaccion.estado,
            'iniciada_en': transaccion.iniciada_en.isoformat(),
            'terminada_en': transaccion.terminada_en.isoformat() if transaccion.terminada_en else None,
            'pasos': [
                {
                    'servicio': p.servicio, 'paso': p.paso, 'direccion': p.direccion,
                    'ocurrido_en': p.ocurrido_en.isoformat(),
                }
                for p in pasos
            ],
        })


@ejecutar_query.register(ObtenerSaga)
def ejecutar_query_obtener_saga(query: ObtenerSaga):
    return ObtenerSagaHandler().handle(query)
