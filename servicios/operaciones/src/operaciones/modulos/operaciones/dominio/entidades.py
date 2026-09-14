"""Agregación del módulo Operaciones (§4.2 de la especificación).

No importa nada de `gestion_trabajos`: se entera de que existe un trabajo
porque su capa anticorrupción traduce un evento de integración a un comando
propio, nunca porque lea el modelo de otro servicio.
"""
from dataclasses import dataclass, field

from operaciones.seedwork.dominio.entidades import AgregacionRaiz

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
