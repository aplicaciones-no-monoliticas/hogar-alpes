"""Consulta ObtenerResumenSagas — `GET /sagas/resumen` (FR-013): cuántas
transacciones hay en cada estado, incluido `INCOMPLETA` calculada (D9).
"""
from dataclasses import dataclass

from saga_log.config.umbral import umbral_incompleta_segundos
from saga_log.seedwork.aplicacion.queries import Query, QueryHandler, QueryResultado, ejecutar_query

from ...infraestructura.repositorios import RepositorioSagas

ESTADOS = ('EN_CURSO', 'COMPLETADA', 'COMPENSANDO', 'COMPENSADA', 'INCOMPLETA')


@dataclass
class ObtenerResumenSagas(Query):
    ...


class ObtenerResumenSagasHandler(QueryHandler):
    def handle(self, query: ObtenerResumenSagas) -> QueryResultado:
        repo = RepositorioSagas()
        conteos = repo.contar_por_estado()
        incompletas = repo.obtener_incompletas(umbral_incompleta_segundos())
        # Categorías mutuamente excluyentes: una transacción `EN_CURSO`/
        # `COMPENSANDO` más vieja que el umbral cuenta como INCOMPLETA, no
        # también bajo su estado persistido (D9).
        por_incompleta: dict[str, int] = {}
        for t in incompletas:
            por_incompleta[t.estado] = por_incompleta.get(t.estado, 0) + 1

        resumen = {
            estado: conteos.get(estado, 0) - por_incompleta.get(estado, 0)
            for estado in ESTADOS if estado != 'INCOMPLETA'
        }
        resumen['INCOMPLETA'] = len(incompletas)
        return QueryResultado(resultado=resumen)


@ejecutar_query.register(ObtenerResumenSagas)
def ejecutar_query_obtener_resumen(query: ObtenerResumenSagas):
    return ObtenerResumenSagasHandler().handle(query)
