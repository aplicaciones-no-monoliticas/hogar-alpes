"""Mapeadores de infraestructura:

- `MapeadorEmparejamiento` — dominio <-> modelo de persistencia.
- `MapeadorEmparejamientoIntegracion` — evento de dominio -> esquema Avro
  `EventoEmparejamiento` (integración, `evt-emparejamiento`).
"""
import uuid

from emparejamiento.seedwork.infraestructura import correlacion
from emparejamiento.seedwork.infraestructura.schema.v1.mensajes import sobre

from ..dominio.entidades import Emparejamiento
from ..dominio.objetos_valor import Candidato, CriterioBusqueda
from .schema.v1.evt_emparejamiento import (
    TIPO_CANDIDATOS,
    TIPO_CANDIDATOS_LIBERADOS,
    TIPO_PROVEEDOR_PROPUESTO,
    TIPO_SIN_CANDIDATOS,
    EventoEmparejamiento,
)
from . import dto as modelo


class MapeadorEmparejamiento:
    def entidad_a_dto(self, entidad: Emparejamiento) -> modelo.Emparejamiento:
        return modelo.Emparejamiento(
            trabajo_id=str(entidad.trabajo_id),
            region=entidad.region,
            categoria=entidad.criterio.categoria,
            pais=entidad.criterio.pais,
            ciudad=entidad.criterio.ciudad,
            candidatos=[c.proveedor_id for c in entidad.candidatos],
            total=len(entidad.candidatos),
            proveedor_reservado=entidad.proveedor_reservado,
        )

    def dto_a_entidad(self, dto: modelo.Emparejamiento) -> Emparejamiento:
        trabajo_id = uuid.UUID(dto.trabajo_id)
        entidad = Emparejamiento(id=trabajo_id, trabajo_id=trabajo_id, region=dto.region)
        entidad.criterio = CriterioBusqueda(categoria=dto.categoria, pais=dto.pais, ciudad=dto.ciudad)
        entidad.candidatos = [Candidato(proveedor_id=p, nivel='') for p in dto.candidatos]
        entidad.proveedor_reservado = dto.proveedor_reservado
        return entidad


class MapeadorEmparejamientoIntegracion:
    """Lo que consume el `Despachador` de la plantilla:
    `entidad_a_dto(evento)` devuelve `(mensaje, schema)`."""

    def entidad_a_dto(self, evento):
        nombre = type(evento).__name__

        if nombre == 'CandidatosIdentificados':
            mensaje = EventoEmparejamiento(
                **sobre(TIPO_CANDIDATOS, 'emparejamiento', correlation_id=correlacion.actual()),
                trabajo_id=str(evento.trabajo_id),
                region=evento.region,
                categoria=evento.categoria,
                pais=evento.pais,
                ciudad=evento.ciudad,
                total_candidatos=len(evento.proveedores_id),
                candidatos=list(evento.proveedores_id),
                proveedor_id='',
                motivo='',
            )
            return mensaje, EventoEmparejamiento

        if nombre == 'SinCandidatos':
            mensaje = EventoEmparejamiento(
                **sobre(TIPO_SIN_CANDIDATOS, 'emparejamiento', correlation_id=correlacion.actual()),
                trabajo_id=str(evento.trabajo_id),
                region=evento.region,
                categoria=evento.categoria,
                pais=evento.pais,
                ciudad=evento.ciudad,
                total_candidatos=0,
                candidatos=[],
                proveedor_id='',
                motivo='',
            )
            return mensaje, EventoEmparejamiento

        if nombre == 'ProveedorPropuesto':
            mensaje = EventoEmparejamiento(
                **sobre(TIPO_PROVEEDOR_PROPUESTO, 'emparejamiento', correlation_id=correlacion.actual()),
                trabajo_id=str(evento.trabajo_id),
                region=evento.region,
                categoria=evento.categoria,
                pais=evento.pais,
                ciudad=evento.ciudad,
                total_candidatos=len(evento.candidatos),
                candidatos=list(evento.candidatos),
                proveedor_id=evento.proveedor_id,
                motivo='',
            )
            return mensaje, EventoEmparejamiento

        if nombre == 'CandidatosLiberados':
            mensaje = EventoEmparejamiento(
                **sobre(TIPO_CANDIDATOS_LIBERADOS, 'emparejamiento', correlation_id=correlacion.actual()),
                trabajo_id=str(evento.trabajo_id),
                region=evento.region,
                categoria='',
                pais='',
                ciudad='',
                total_candidatos=0,
                candidatos=[],
                proveedor_id=evento.proveedor_id,
                motivo=evento.motivo,
            )
            return mensaje, EventoEmparejamiento

        raise NotImplementedError(f'No hay esquema de integración para {nombre}')
