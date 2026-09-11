import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .eventos import EventoDominio


@dataclass
class Entidad:
    """Objeto de dominio con identidad propia y ciclo de vida."""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    fecha_creacion: datetime = field(default_factory=datetime.utcnow)
    fecha_actualizacion: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def siguiente_id(cls) -> uuid.UUID:
        return uuid.uuid4()

    def __eq__(self, other) -> bool:
        if not isinstance(other, Entidad):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class AgregacionRaiz(Entidad):
    """Única puerta de entrada al agregado.

    Acumula los eventos de dominio producidos por sus mutaciones. La Unidad de
    Trabajo los recoge y los publica: nada dentro del dominio conoce el broker.
    """
    eventos: list[EventoDominio] = field(default_factory=list)

    def agregar_evento(self, evento: EventoDominio):
        self.eventos.append(evento)

    def limpiar_eventos(self):
        self.eventos = list()
