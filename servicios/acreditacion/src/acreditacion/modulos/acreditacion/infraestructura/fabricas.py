"""Fábrica de repositorios: el único lugar del servicio que sabe que el event
store vive en PostgreSQL."""
from dataclasses import dataclass

from acreditacion.seedwork.dominio.excepciones import TipoObjetoNoExisteEnDominioExcepcion
from acreditacion.seedwork.dominio.fabricas import Fabrica

from ..dominio.repositorios import RepositorioAcreditaciones
from .repositorios import RepositorioAcreditacionesEventSourcing


@dataclass
class FabricaRepositorio(Fabrica):
    def crear_objeto(self, obj, mapeador=None):
        if obj == RepositorioAcreditaciones:
            return RepositorioAcreditacionesEventSourcing()
        raise TipoObjetoNoExisteEnDominioExcepcion()
