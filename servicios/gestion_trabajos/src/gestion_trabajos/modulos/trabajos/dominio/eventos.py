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
    # Marca de demostración de la saga (Entrega 5, D3 de
    # specs/002-saga-asignacion-trabajo/research.md): nunca forma parte del
    # contrato Avro, viaja solo como propiedad del mensaje.
    simular_fallo: str = ''


@dataclass
class EstadoTrabajoCambiado(EventoDominio):
    trabajo_id: uuid.UUID = None
    estado_anterior: str = ''
    estado_nuevo: str = ''
    # Contexto del trabajo. Hace falta por dos razones: para enrutar el evento
    # al stream de SU región —si la creación y el cambio de estado cayeran en
    # streams distintos se perdería el orden dentro del trabajo (brecha G-2)— y
    # para que el consumidor no tenga que preguntarle nada a este servicio.
    pais: str = ''
    ciudad: str = ''
    canal: str = ''
    partner_id: str = ''
    categoria: str = ''
    urgencia: str = ''
    simular_fallo: str = ''


@dataclass
class SubTrabajoAgregado(EventoDominio):
    trabajo_id: uuid.UUID = None
    sub_trabajo_id: uuid.UUID = None
    categoria: str = ''
