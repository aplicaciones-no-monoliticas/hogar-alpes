"""Mapeadores de infraestructura: dominio <-> modelo de persistencia, y
dominio -> esquema Avro del evento de integración."""
import uuid
from datetime import datetime

from gestion_trabajos.seedwork.dominio.repositorios import Mapeador
from gestion_trabajos.seedwork.infraestructura.utils import unix_time_millis

from ..dominio.entidades import SubTrabajo, Trabajo
from ..dominio.objetos_valor import (
    Canal,
    Categoria,
    Estado,
    EstadoTrabajo,
    Solicitante,
    Ubicacion,
    Urgencia,
)
from . import dto as modelo
from .schema.v1.eventos import (
    EstadoTrabajoCambiadoPayload,
    EventoEstadoTrabajoCambiado,
    EventoTrabajoCreado,
    TrabajoCreadoPayload,
)


class MapeadorTrabajo(Mapeador):
    def obtener_tipo(self) -> type:
        return Trabajo

    def entidad_a_dto(self, entidad: Trabajo) -> modelo.Trabajo:
        return modelo.Trabajo(
            id=str(entidad.id),
            fecha_creacion=entidad.fecha_creacion,
            fecha_actualizacion=entidad.fecha_actualizacion,
            canal=entidad.solicitante.canal.value,
            partner_id=entidad.solicitante.partner_id,
            referencia_externa=entidad.solicitante.referencia_externa,
            categoria=entidad.categoria.codigo,
            urgencia=entidad.urgencia.nivel,
            pais=entidad.ubicacion.pais,
            ciudad=entidad.ubicacion.ciudad,
            direccion=entidad.ubicacion.direccion,
            descripcion=entidad.descripcion,
            estado=entidad.estado.valor.value,
            sub_trabajos=[
                modelo.SubTrabajo(
                    id=str(s.id),
                    trabajo_id=str(entidad.id),
                    descripcion=s.descripcion,
                    categoria=s.categoria.codigo,
                    estado=s.estado.valor.value,
                )
                for s in entidad.sub_trabajos
            ],
        )

    def dto_a_entidad(self, dto: modelo.Trabajo) -> Trabajo:
        trabajo = Trabajo(
            id=uuid.UUID(dto.id),
            fecha_creacion=dto.fecha_creacion,
            fecha_actualizacion=dto.fecha_actualizacion,
            solicitante=Solicitante(
                canal=Canal(dto.canal),
                partner_id=dto.partner_id or '',
                referencia_externa=dto.referencia_externa or '',
            ),
            categoria=Categoria(codigo=dto.categoria),
            urgencia=Urgencia(nivel=dto.urgencia),
            ubicacion=Ubicacion(pais=dto.pais, ciudad=dto.ciudad, direccion=dto.direccion),
            descripcion=dto.descripcion or '',
            estado=EstadoTrabajo(Estado(dto.estado)),
        )
        trabajo.sub_trabajos = [
            SubTrabajo(
                id=uuid.UUID(s.id),
                descripcion=s.descripcion or '',
                categoria=Categoria(codigo=s.categoria),
                estado=EstadoTrabajo(Estado(s.estado)),
            )
            for s in dto.sub_trabajos
        ]
        return trabajo


class MapeadorEventosTrabajo(Mapeador):
    """Traduce un evento de dominio al evento de integración versionado (v1)."""

    versions = ('v1',)
    LATEST_VERSION = versions[0]

    def obtener_tipo(self) -> type:
        return EventoTrabajoCreado

    def _envelope(self, evento, tipo: str) -> dict:
        return dict(
            id=str(evento.id),
            time=unix_time_millis(evento.fecha_evento),
            specversion='v1',
            type=tipo,
            ingestion=unix_time_millis(datetime.utcnow()),
            datacontenttype='AVRO',
            service_name='gestion-trabajos',
        )

    def entidad_a_dto(self, evento):
        nombre = type(evento).__name__

        if nombre == 'TrabajoCreado':
            payload = TrabajoCreadoPayload(
                trabajo_id=str(evento.trabajo_id),
                categoria=evento.categoria,
                urgencia=evento.urgencia,
                pais=evento.pais,
                ciudad=evento.ciudad,
                canal=evento.canal,
                partner_id=evento.partner_id,
                estado=evento.estado,
            )
            return (
                EventoTrabajoCreado(data=payload, **self._envelope(evento, 'TrabajoCreado')),
                EventoTrabajoCreado,
            )

        if nombre == 'EstadoTrabajoCambiado':
            payload = EstadoTrabajoCambiadoPayload(
                trabajo_id=str(evento.trabajo_id),
                estado_anterior=evento.estado_anterior,
                estado_nuevo=evento.estado_nuevo,
            )
            return (
                EventoEstadoTrabajoCambiado(
                    data=payload, **self._envelope(evento, 'EstadoTrabajoCambiado')
                ),
                EventoEstadoTrabajoCambiado,
            )

        raise NotImplementedError(f'No hay esquema de integración para {nombre}')

    def dto_a_entidad(self, dto):
        raise NotImplementedError
