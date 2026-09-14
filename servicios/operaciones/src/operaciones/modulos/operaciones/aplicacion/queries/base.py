from operaciones.seedwork.aplicacion.queries import QueryHandler

from ...infraestructura.fabricas import FabricaRepositorio


class OperacionesQueryBaseHandler(QueryHandler):
    def __init__(self):
        self._fabrica_repositorio = FabricaRepositorio()

    @property
    def fabrica_repositorio(self):
        return self._fabrica_repositorio
