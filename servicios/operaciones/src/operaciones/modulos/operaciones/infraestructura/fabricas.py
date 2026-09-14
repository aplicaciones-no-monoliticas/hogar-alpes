"""Fábrica de repositorios: el único lugar del servicio que sabe que la
persistencia es PostgreSQL."""
from dataclasses import dataclass

from operaciones.seedwork.dominio.excepciones import TipoObjetoNoExisteEnDominioExcepcion
from operaciones.seedwork.dominio.fabricas import Fabrica

from ..dominio.repositorios import RepositorioEventosProcesados, RepositorioSeguimientos
from .repositorios import RepositorioEventosProcesadosPostgres, RepositorioSeguimientosPostgres


@dataclass
class FabricaRepositorio(Fabrica):
    def crear_objeto(self, obj, mapeador=None):
        if obj == RepositorioSeguimientos:
            return RepositorioSeguimientosPostgres()
        if obj == RepositorioEventosProcesados:
            return RepositorioEventosProcesadosPostgres()
        raise TipoObjetoNoExisteEnDominioExcepcion()
