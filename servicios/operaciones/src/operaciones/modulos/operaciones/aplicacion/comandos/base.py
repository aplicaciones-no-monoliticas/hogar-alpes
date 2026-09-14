from operaciones.seedwork.aplicacion.comandos import ComandoHandler

from ...infraestructura.fabricas import FabricaRepositorio


class OperacionesBaseHandler(ComandoHandler):
    def __init__(self):
        self._fabrica_repositorio = FabricaRepositorio()

    @property
    def fabrica_repositorio(self):
        return self._fabrica_repositorio
