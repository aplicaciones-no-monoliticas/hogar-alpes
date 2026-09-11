"""Fábrica que traduce un evento entrante en la agregación del módulo.

Aquí vive la política de SLA de Operaciones. Que la urgencia CRITICA sean 60
minutos es una decisión de este módulo, no de `trabajos`.
"""
from dataclasses import dataclass

from gestion_trabajos.seedwork.dominio.fabricas import Fabrica

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
            trabajo_id=str(obj.trabajo_id),
            pais=obj.pais,
            canal=obj.canal,
            categoria=obj.categoria,
            estado_trabajo=obj.estado,
            ventana_sla=POLITICA_SLA.get(obj.urgencia, POLITICA_SLA['NORMAL']),
        )
        seguimiento.abrir()
        return seguimiento
