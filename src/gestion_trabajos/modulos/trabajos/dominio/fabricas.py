"""Fábrica del agregado Trabajo.

Garantiza que un Trabajo nunca exista en un estado inválido: si una regla falla,
la agregación no llega a construirse.
"""
from dataclasses import dataclass

from gestion_trabajos.seedwork.dominio.entidades import Entidad
from gestion_trabajos.seedwork.dominio.fabricas import Fabrica
from gestion_trabajos.seedwork.dominio.repositorios import Mapeador
from gestion_trabajos.seedwork.dominio.excepciones import (
    TipoObjetoNoExisteEnDominioTrabajosExcepcion,
)

from .entidades import Trabajo


@dataclass
class _FabricaTrabajo(Fabrica):
    def crear_objeto(self, obj, mapeador: Mapeador = None) -> any:
        if isinstance(obj, Entidad):
            return mapeador.entidad_a_dto(obj)
        return mapeador.dto_a_entidad(obj)


@dataclass
class FabricaTrabajos(Fabrica):
    def crear_objeto(self, obj, mapeador: Mapeador = None) -> any:
        if mapeador.obtener_tipo() == Trabajo:
            return _FabricaTrabajo().crear_objeto(obj, mapeador)
        raise TipoObjetoNoExisteEnDominioTrabajosExcepcion()
