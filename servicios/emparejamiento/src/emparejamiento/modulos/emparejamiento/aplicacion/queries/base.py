from emparejamiento.seedwork.aplicacion.queries import QueryHandler

from ...infraestructura.fabricas import FabricaRepositorio


class EmparejamientoQueryBaseHandler(QueryHandler):
    def __init__(self):
        self._fabrica_repositorio = FabricaRepositorio()

    @property
    def fabrica_repositorio(self):
        return self._fabrica_repositorio
