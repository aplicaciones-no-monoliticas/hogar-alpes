import uuid
from dataclasses import dataclass

from gestion_trabajos.seedwork.dominio.eventos import EventoDominio


@dataclass
class SeguimientoAbierto(EventoDominio):
    seguimiento_id: uuid.UUID = None
    trabajo_id: str = ''
    prioridad: str = ''
