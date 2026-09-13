"""Fábrica del agregado Emparejamiento."""
import uuid
from dataclasses import dataclass

from emparejamiento.seedwork.dominio.fabricas import Fabrica

from .entidades import Emparejamiento
from .excepciones import EmparejamientoNoExisteExcepcion


@dataclass
class FabricaEmparejamientos(Fabrica):
    def crear_objeto(self, obj, mapeador=None) -> Emparejamiento:
        if not isinstance(obj, dict):
            raise EmparejamientoNoExisteExcepcion(
                'La fábrica de Emparejamiento espera los datos del trabajo'
            )
        trabajo_id = uuid.UUID(str(obj['trabajo_id']))
        return Emparejamiento(id=trabajo_id, trabajo_id=trabajo_id, region=obj.get('region', ''))
