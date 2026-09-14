"""Evento de DOMINIO del módulo. Sigue existiendo en proceso, aunque en la
Entrega 4 Operaciones no publica ningún evento de integración (§4.2 de la
especificación): es el reactor final de la transacción larga de referencia,
no la emite.
"""
import uuid
from dataclasses import dataclass

from operaciones.seedwork.dominio.eventos import EventoDominio


@dataclass
class SeguimientoAbierto(EventoDominio):
    seguimiento_id: uuid.UUID = None
    trabajo_id: str = ''
    prioridad: str = ''
