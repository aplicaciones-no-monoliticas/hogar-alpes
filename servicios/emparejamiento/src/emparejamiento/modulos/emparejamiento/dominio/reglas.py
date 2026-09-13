"""Reglas de negocio de la agregación Emparejamiento."""
from emparejamiento.seedwork.dominio.reglas import ReglaNegocio

from .objetos_valor import CriterioBusqueda


class CriterioBusquedaCompleto(ReglaNegocio):
    def __init__(self, criterio: CriterioBusqueda, mensaje='El criterio de búsqueda está incompleto'):
        super().__init__(mensaje)
        self.criterio = criterio

    def es_valido(self) -> bool:
        return bool(self.criterio.categoria and self.criterio.pais and self.criterio.ciudad)
