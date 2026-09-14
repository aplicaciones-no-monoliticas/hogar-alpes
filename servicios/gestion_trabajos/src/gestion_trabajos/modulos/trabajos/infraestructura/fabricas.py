"""Fábrica de repositorios: el punto donde se ata el puerto a un adaptador.

**Es el único archivo que sabe qué motor de persistencia usa el servicio**
(MOD-1, CA-M1). `ADAPTADOR_TRABAJOS=postgres` (por defecto) o `memoria`
—la variable que reemplaza el adaptador— es la medida del escenario: 0
archivos de `dominio/` ni `aplicacion/` cambian cuando se agrega o se elige un
adaptador nuevo, verificable con `git diff --stat` sobre esas dos carpetas.
"""
import os
from dataclasses import dataclass

from gestion_trabajos.seedwork.dominio.excepciones import (
    TipoObjetoNoExisteEnDominioTrabajosExcepcion,
)
from gestion_trabajos.seedwork.dominio.fabricas import Fabrica
from gestion_trabajos.seedwork.dominio.repositorios import Repositorio

from ..dominio.repositorios import RepositorioTrabajos
from .repositorios import RepositorioTrabajosPostgres
from .repositorios_memoria import RepositorioTrabajosMemoria


@dataclass
class FabricaRepositorio(Fabrica):
    def crear_objeto(self, obj, mapeador=None) -> Repositorio:
        if obj == RepositorioTrabajos:
            adaptador = os.getenv('ADAPTADOR_TRABAJOS', 'postgres')
            if adaptador == 'memoria':
                return RepositorioTrabajosMemoria()
            if adaptador == 'postgres':
                return RepositorioTrabajosPostgres()
            raise TipoObjetoNoExisteEnDominioTrabajosExcepcion(
                f'ADAPTADOR_TRABAJOS desconocido: {adaptador!r}'
            )
        raise TipoObjetoNoExisteEnDominioTrabajosExcepcion()
