"""Eventos de DOMINIO del módulo trabajos.

Nombrados en pretérito, según la convención fijada en la vista funcional C&C
(HDA-003) de la Entrega 2. No están versionados: el versionamiento es cosa de
los eventos de integración, que sí cruzan el límite del servicio.
"""
import uuid
from dataclasses import dataclass, field

from gestion_trabajos.seedwork.dominio.eventos import EventoDominio


@dataclass
class TrabajoCreado(EventoDominio):
    trabajo_id: uuid.UUID = None
    categoria: str = ''
    urgencia: str = ''
    pais: str = ''
    ciudad: str = ''
    canal: str = ''
    partner_id: str = ''
    estado: str = ''


@dataclass
class EstadoTrabajoCambiado(EventoDominio):
    trabajo_id: uuid.UUID = None
    estado_anterior: str = ''
    estado_nuevo: str = ''


@dataclass
class SubTrabajoAgregado(EventoDominio):
    trabajo_id: uuid.UUID = None
    sub_trabajo_id: uuid.UUID = None
    categoria: str = ''
