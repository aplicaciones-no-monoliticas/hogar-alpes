"""Eventos de DOMINIO del módulo emparejamiento. Nombrados en pretérito, igual
que en Gestión de Trabajos. Cada uno lleva lo que necesita el evento de
integración `evt-emparejamiento` — el mapeador de infraestructura los traduce
campo a campo."""
import uuid
from dataclasses import dataclass, field

from emparejamiento.seedwork.dominio.eventos import EventoDominio


@dataclass
class CandidatosIdentificados(EventoDominio):
    trabajo_id: uuid.UUID = None
    region: str = ''
    categoria: str = ''
    pais: str = ''
    ciudad: str = ''
    proveedores_id: list[str] = field(default_factory=list)


@dataclass
class SinCandidatos(EventoDominio):
    trabajo_id: uuid.UUID = None
    region: str = ''
    categoria: str = ''
    pais: str = ''
    ciudad: str = ''
    simular_fallo: str = ''


@dataclass
class ProveedorPropuesto(EventoDominio):
    """Saga (Entrega 5, D1 de research.md): el único candidato que logró
    reservarse para este trabajo. `candidatos` sigue siendo la lista completa
    ya identificada, para no perder ese dato en el evento de integración."""
    trabajo_id: uuid.UUID = None
    region: str = ''
    categoria: str = ''
    pais: str = ''
    ciudad: str = ''
    candidatos: list[str] = field(default_factory=list)
    proveedor_id: str = ''
    simular_fallo: str = ''


@dataclass
class CandidatosLiberados(EventoDominio):
    """Saga (Entrega 5): reversión de `ProveedorPropuesto`. `motivo` es
    `VIGENCIA_RECHAZADA` · `ASIGNACION_FALLIDA` (ver contracts/evt-emparejamiento.md)."""
    trabajo_id: uuid.UUID = None
    region: str = ''
    proveedor_id: str = ''
    motivo: str = ''
