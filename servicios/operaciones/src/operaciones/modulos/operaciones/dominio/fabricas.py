"""Fábrica que traduce un `TrabajoCreado` entrante en la agregación del
módulo. Aquí vive la política de SLA de Operaciones: que la urgencia CRITICA
sean 60 minutos es una decisión de este servicio, no de `gestion_trabajos`.
"""
from dataclasses import dataclass

from operaciones.seedwork.dominio.fabricas import Fabrica

from .entidades import SeguimientoOperativo
from .objetos_valor import Prioridad, VentanaSLA

POLITICA_SLA = {
    'CRITICA': VentanaSLA(minutos=60, prioridad=Prioridad.P1),
    'ALTA': VentanaSLA(minutos=240, prioridad=Prioridad.P2),
    'NORMAL': VentanaSLA(minutos=1440, prioridad=Prioridad.P3),
    'BAJA': VentanaSLA(minutos=4320, prioridad=Prioridad.P3),
}


@dataclass
class FabricaSeguimientos(Fabrica):
    def crear_objeto(self, obj, mapeador=None) -> SeguimientoOperativo:
        seguimiento = SeguimientoOperativo(
            trabajo_id=str(obj['trabajo_id']),
            pais=obj.get('pais', ''),
            canal=obj.get('canal', ''),
            categoria=obj.get('categoria', ''),
            estado_trabajo=obj.get('estado', ''),
            ventana_sla=POLITICA_SLA.get(obj.get('urgencia'), POLITICA_SLA['NORMAL']),
        )
        seguimiento.abrir()
        return seguimiento
