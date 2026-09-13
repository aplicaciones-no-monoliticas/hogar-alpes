"""Objetos valor del contexto Acreditación.

`EstadoAcreditacion` encapsula el ciclo de vida `SOLICITADA → ACREDITADA →
REVOCADA | VENCIDA` (01-especificacion.md §4.4). Igual que `EstadoTrabajo` en
Gestión de Trabajos, la agregación no conoce el grafo de transiciones: solo
pregunta. `VENCIDA` queda modelada aquí porque es parte del ciclo de vida
declarado; la transición automática por vencimiento de `vigente_hasta` es
candidata natural de la Entrega 5 (verificar vigencia antes de asignar, `PS-10`)
y no la dispara ningún comando de la Entrega 4.
"""
from dataclasses import dataclass
from enum import Enum

from acreditacion.seedwork.dominio.objetos_valor import ObjetoValor


class Estado(str, Enum):
    SOLICITADA = 'SOLICITADA'
    ACREDITADA = 'ACREDITADA'
    REVOCADA = 'REVOCADA'
    VENCIDA = 'VENCIDA'


TRANSICIONES: dict[Estado, set[Estado]] = {
    Estado.SOLICITADA: {Estado.ACREDITADA},
    Estado.ACREDITADA: {Estado.REVOCADA, Estado.VENCIDA},
    Estado.REVOCADA: set(),
    Estado.VENCIDA: set(),
}


@dataclass(frozen=True)
class EstadoAcreditacion(ObjetoValor):
    valor: Estado = Estado.SOLICITADA

    def puede_transicionar_a(self, destino: Estado) -> bool:
        return destino in TRANSICIONES.get(self.valor, set())


@dataclass(frozen=True)
class Homologacion(ObjetoValor):
    """Categoría (oficio regulado) para la que se certifica al proveedor."""
    categoria: str = ''


@dataclass(frozen=True)
class NivelAcreditacion(ObjetoValor):
    """Texto abierto a propósito (RS-5): una enumeración cerrada aquí sería el
    mismo error que una enumeración cerrada de estado en Gestión de Trabajos."""
    codigo: str = ''


@dataclass(frozen=True)
class Vigencia(ObjetoValor):
    meses: int = 0
    vigente_hasta: str = ''  # ISO-8601 (YYYY-MM-DD); vacío hasta que se aprueba
