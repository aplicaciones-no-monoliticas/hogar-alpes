from dataclasses import dataclass

from gestion_trabajos.seedwork.dominio.excepciones import (
    TipoObjetoNoExisteEnDominioTrabajosExcepcion,
)
from gestion_trabajos.seedwork.dominio.fabricas import Fabrica
from gestion_trabajos.seedwork.dominio.repositorios import Repositorio

from ..dominio.repositorios import RepositorioSeguimientos
from .repositorios import RepositorioSeguimientosPostgres


@dataclass
class FabricaRepositorioSeguimientos(Fabrica):
    def crear_objeto(self, obj, mapeador=None) -> Repositorio:
        if obj == RepositorioSeguimientos:
            return RepositorioSeguimientosPostgres()
        raise TipoObjetoNoExisteEnDominioTrabajosExcepcion()
