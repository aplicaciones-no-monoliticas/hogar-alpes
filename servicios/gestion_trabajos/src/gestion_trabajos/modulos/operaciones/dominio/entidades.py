"""Agregación del módulo Operaciones.

No importa nada del módulo `trabajos`: se entera de que existe un trabajo porque
recibe un evento de dominio, no porque lea su modelo. Ese es el aislamiento que
la rúbrica pide.
"""
from dataclasses import dataclass, field

from gestion_trabajos.seedwork.dominio.entidades import AgregacionRaiz

from .eventos import SeguimientoAbierto
from .objetos_valor import Prioridad, VentanaSLA


@dataclass
class SeguimientoOperativo(AgregacionRaiz):
    trabajo_id: str = ''
    pais: str = ''
    canal: str = ''
    categoria: str = ''
    estado_trabajo: str = ''
    ventana_sla: VentanaSLA = field(default_factory=VentanaSLA)

    def abrir(self):
        self.agregar_evento(
            SeguimientoAbierto(
                seguimiento_id=self.id,
                trabajo_id=self.trabajo_id,
                prioridad=self.ventana_sla.prioridad.value,
            )
        )

    def registrar_cambio_estado(self, estado_nuevo: str):
        self.estado_trabajo = estado_nuevo
