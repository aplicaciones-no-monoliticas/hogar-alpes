"""Fábrica de repositorios: el único lugar del servicio que sabe que la
persistencia es PostgreSQL."""
from dataclasses import dataclass

from emparejamiento.seedwork.dominio.excepciones import TipoObjetoNoExisteEnDominioExcepcion
from emparejamiento.seedwork.dominio.fabricas import Fabrica

from ..dominio.repositorios import (
    RepositorioEmparejamientos,
    RepositorioProveedoresCandidatos,
    RepositorioReservasProveedor,
)
from .repositorios import (
    RepositorioEmparejamientosPostgres,
    RepositorioProveedoresCandidatosPostgres,
    RepositorioReservasProveedorPostgres,
)


@dataclass
class FabricaRepositorio(Fabrica):
    def crear_objeto(self, obj, mapeador=None):
        if obj == RepositorioEmparejamientos:
            return RepositorioEmparejamientosPostgres()
        if obj == RepositorioProveedoresCandidatos:
            return RepositorioProveedoresCandidatosPostgres()
        if obj == RepositorioReservasProveedor:
            return RepositorioReservasProveedorPostgres()
        raise TipoObjetoNoExisteEnDominioExcepcion()
