from gestion_trabajos.seedwork.aplicacion.queries import QueryHandler

from ...infraestructura.fabricas import FabricaRepositorio
from ...dominio.fabricas import FabricaTrabajos


class TrabajoQueryBaseHandler(QueryHandler):
    def __init__(self):
        self._fabrica_repositorio = FabricaRepositorio()
        self._fabrica_trabajos = FabricaTrabajos()

    @property
    def fabrica_repositorio(self):
        return self._fabrica_repositorio

    @property
    def fabrica_trabajos(self):
        return self._fabrica_trabajos
