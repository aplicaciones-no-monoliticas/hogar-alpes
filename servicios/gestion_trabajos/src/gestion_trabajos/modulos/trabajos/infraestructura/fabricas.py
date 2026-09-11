"""Fábrica de repositorios: el punto donde se ata el puerto a un adaptador.

Es el único lugar del servicio que sabe que la persistencia es PostgreSQL.
"""
from dataclasses import dataclass

from gestion_trabajos.seedwork.dominio.excepciones import (
    TipoObjetoNoExisteEnDominioTrabajosExcepcion,
)
from gestion_trabajos.seedwork.dominio.fabricas import Fabrica
from gestion_trabajos.seedwork.dominio.repositorios import Repositorio

from ..dominio.repositorios import RepositorioTrabajos
from .repositorios import RepositorioTrabajosPostgres


@dataclass
class FabricaRepositorio(Fabrica):
    def crear_objeto(self, obj, mapeador=None) -> Repositorio:
        if obj == RepositorioTrabajos:
            return RepositorioTrabajosPostgres()
        raise TipoObjetoNoExisteEnDominioTrabajosExcepcion()
