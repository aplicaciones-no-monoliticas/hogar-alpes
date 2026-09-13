"""Eventos de DOMINIO del módulo acreditación.

A diferencia de Gestión de Trabajos, cada evento lleva el **estado completo**
del agregado en el momento en que ocurre, no solo el delta. Dos razones:

1. Son la fuente de verdad del event store (ACR-2): reproducirlos en orden
   reconstruye la agregación exactamente, sin necesitar un snapshot aparte.
2. Son también el material del evento de INTEGRACIÓN `AcreditacionActualizada`
   (carga de estado, `evt-acreditacion`): el mapeador de infraestructura los
   traduce campo a campo, sin tener que releer el agregado tras el commit.

`version` es la posición del evento en el log de este agregado — la asigna la
propia agregación al emitirlo (`Acreditacion._registrar_evento`), no el
repositorio. Es lo que hace de `UNIQUE(agregado_id, version)` un control de
concurrencia optimista real: dos comandos concurrentes que parten del mismo
estado calculan la misma versión siguiente, y solo uno gana la escritura.
"""
import uuid
from dataclasses import dataclass, field

from acreditacion.seedwork.dominio.eventos import EventoDominio


@dataclass
class EventoAcreditacion(EventoDominio):
    """Snapshot común a los tres eventos: agregado_id + el estado completo."""
    agregado_id: uuid.UUID = None
    version: int = 0
    proveedor_id: str = ''
    pais: str = ''
    ciudad: str = ''
    categorias: list[str] = field(default_factory=list)
    nivel: str = ''
    vigencia_meses: int = 0
    estado: str = ''
    vigente_hasta: str = ''
    motivo: str = ''


@dataclass
class AcreditacionSolicitada(EventoAcreditacion):
    ...


@dataclass
class AcreditacionAprobada(EventoAcreditacion):
    ...


@dataclass
class AcreditacionRevocada(EventoAcreditacion):
    ...


# Índice tipo -> clase, usado por la infraestructura para deserializar el
# event store (columna `tipo`) de vuelta a un evento de dominio reproducible.
TIPOS_EVENTO = {
    'AcreditacionSolicitada': AcreditacionSolicitada,
    'AcreditacionAprobada': AcreditacionAprobada,
    'AcreditacionRevocada': AcreditacionRevocada,
}
