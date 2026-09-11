from dataclasses import dataclass, field

from gestion_trabajos.seedwork.aplicacion.dto import DTO


@dataclass(frozen=True)
class SubTrabajoDTO(DTO):
    id: str = ''
    descripcion: str = ''
    categoria: str = ''
    estado: str = ''


@dataclass(frozen=True)
class TrabajoDTO(DTO):
    id: str = ''
    fecha_creacion: str = ''
    fecha_actualizacion: str = ''
    canal: str = ''
    partner_id: str = ''
    referencia_externa: str = ''
    categoria: str = ''
    urgencia: str = ''
    pais: str = ''
    ciudad: str = ''
    direccion: str = ''
    descripcion: str = ''
    estado: str = ''
    sub_trabajos: list[SubTrabajoDTO] = field(default_factory=list)
