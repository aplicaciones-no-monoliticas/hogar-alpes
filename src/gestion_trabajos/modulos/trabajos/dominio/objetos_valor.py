"""Objetos valor del contexto Gestión de Trabajos.

`EstadoTrabajo` encapsula las transiciones válidas del ciclo de vida. Agregar un
estado nuevo (escenario 3) se reduce a tocar este archivo: la agregación no
conoce el grafo de transiciones, solo pregunta.
"""
from dataclasses import dataclass
from enum import Enum

from gestion_trabajos.seedwork.dominio.objetos_valor import ObjetoValor


class Estado(str, Enum):
    CREADO = 'CREADO'
    EMPAREJANDO = 'EMPAREJANDO'
    ASIGNADO = 'ASIGNADO'
    EN_EJECUCION = 'EN_EJECUCION'
    EN_VERIFICACION = 'EN_VERIFICACION'
    COMPLETADO = 'COMPLETADO'
    CANCELADO = 'CANCELADO'


TRANSICIONES: dict[Estado, set[Estado]] = {
    Estado.CREADO: {Estado.EMPAREJANDO, Estado.CANCELADO},
    Estado.EMPAREJANDO: {Estado.ASIGNADO, Estado.CANCELADO},
    Estado.ASIGNADO: {Estado.EN_EJECUCION, Estado.CANCELADO},
    Estado.EN_EJECUCION: {Estado.EN_VERIFICACION, Estado.CANCELADO},
    Estado.EN_VERIFICACION: {Estado.COMPLETADO, Estado.EN_EJECUCION},
    Estado.COMPLETADO: set(),
    Estado.CANCELADO: set(),
}


class Canal(str, Enum):
    MARKETPLACE = 'MARKETPLACE'
    B2B2C = 'B2B2C'


@dataclass(frozen=True)
class EstadoTrabajo(ObjetoValor):
    valor: Estado = Estado.CREADO

    def puede_transicionar_a(self, destino: Estado) -> bool:
        return destino in TRANSICIONES.get(self.valor, set())

    def transiciones_posibles(self) -> set[Estado]:
        return TRANSICIONES.get(self.valor, set())


@dataclass(frozen=True)
class Categoria(ObjetoValor):
    """Genérica a propósito: los valores permitidos los aporta el sidecar
    regional, no el dominio. El dominio no sabe en qué país corre (escenario 2)."""
    codigo: str = ''


@dataclass(frozen=True)
class Urgencia(ObjetoValor):
    nivel: str = 'NORMAL'
    minutos_objetivo: int = 1440


@dataclass(frozen=True)
class Ubicacion(ObjetoValor):
    pais: str = ''
    ciudad: str = ''
    direccion: str = ''


@dataclass(frozen=True)
class Solicitante(ObjetoValor):
    canal: Canal = Canal.MARKETPLACE
    partner_id: str = ''
    referencia_externa: str = ''
