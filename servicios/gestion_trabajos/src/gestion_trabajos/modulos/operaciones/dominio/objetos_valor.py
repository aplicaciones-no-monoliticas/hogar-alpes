from dataclasses import dataclass
from enum import Enum

from gestion_trabajos.seedwork.dominio.objetos_valor import ObjetoValor


class Prioridad(str, Enum):
    P1 = 'P1'
    P2 = 'P2'
    P3 = 'P3'


@dataclass(frozen=True)
class VentanaSLA(ObjetoValor):
    """Minutos objetivo para atender el trabajo, derivados de la urgencia."""
    minutos: int = 1440
    prioridad: Prioridad = Prioridad.P3
