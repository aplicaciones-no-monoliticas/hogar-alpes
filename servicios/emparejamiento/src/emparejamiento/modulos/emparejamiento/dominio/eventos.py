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
