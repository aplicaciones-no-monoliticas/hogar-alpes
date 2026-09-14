"""Consultas de conteo — `GET /seguimientos/conteo?desde=` y el instrumento que
usa `escenarios/escenario-6.sh` para verificar CA-6.4 (seguimientos creados =
N, 0 duplicados) y CA-6.5 (0 eventos huérfanos)."""
from dataclasses import dataclass
from datetime import datetime

from operaciones.seedwork.aplicacion.queries import Query, QueryResultado, ejecutar_query

from ...dominio.repositorios import RepositorioEventosProcesados, RepositorioSeguimientos
from .base import OperacionesQueryBaseHandler


@dataclass
class ContarSeguimientos(Query):
    desde: str = ''  # ISO-8601; vacío = sin filtro


class ContarSeguimientosHandler(OperacionesQueryBaseHandler):
    def handle(self, query: ContarSeguimientos) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioSeguimientos)
        desde = datetime.fromisoformat(query.desde) if query.desde else datetime.min
        return QueryResultado(resultado={'total': repositorio.contar_desde(desde)})


@ejecutar_query.register(ContarSeguimientos)
def ejecutar_query_contar_seguimientos(query: ContarSeguimientos):
    return ContarSeguimientosHandler().handle(query)


@dataclass
class ContarEventosProcesados(Query):
    resultado: str = 'APLICADO'  # APLICADO | DUPLICADO | HUERFANO


class ContarEventosProcesadosHandler(OperacionesQueryBaseHandler):
    def handle(self, query: ContarEventosProcesados) -> QueryResultado:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioEventosProcesados)
        return QueryResultado(resultado={'total': repositorio.contar_por_resultado(query.resultado)})


@ejecutar_query.register(ContarEventosProcesados)
def ejecutar_query_contar_eventos_procesados(query: ContarEventosProcesados):
    return ContarEventosProcesadosHandler().handle(query)
