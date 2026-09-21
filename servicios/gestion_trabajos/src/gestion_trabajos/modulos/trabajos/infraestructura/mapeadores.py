"""Mapeadores de infraestructura: dominio <-> modelo de persistencia, y
dominio -> esquema Avro del evento de integración."""
import uuid
from datetime import datetime

from gestion_trabajos.seedwork.dominio.repositorios import Mapeador
from gestion_trabajos.seedwork.infraestructura import correlacion
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
from .schema.v1.eventos import TIPO_CREADO, TIPO_ESTADO_CAMBIADO, EventoTrabajo


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
            proveedor_id=entidad.proveedor_id,
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
            proveedor_id=dto.proveedor_id,
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
        return EventoTrabajo

    def _sobre(self, evento, tipo: str) -> dict:
        """Los ocho campos del sobre, explícitos. La herencia de `Record` los
        perdía en silencio: ver CON-1 en `docs/decisiones.md`."""
        return dict(
            id=str(evento.id),
            time=unix_time_millis(evento.fecha_evento),
            ingestion=unix_time_millis(datetime.utcnow()),
            specversion='1.0',
            type=tipo,
            datacontenttype='application/avro',
            service_name='gestion-trabajos',
            # Identificador de la petición que originó el evento (TO-4), no el del
            # trabajo: el trabajo ya viaja en `trabajo_id` y en la clave de partición.
            correlation_id=correlacion.actual(),
        )

    def entidad_a_dto(self, evento):
        """Los dos tipos de evento viajan por el MISMO stream, discriminados por
        `type`. Es lo que garantiza el orden dentro de un trabajo (brecha G-2)."""
        nombre = type(evento).__name__

        tipos = {'TrabajoCreado': TIPO_CREADO, 'EstadoTrabajoCambiado': TIPO_ESTADO_CAMBIADO}
        if nombre not in tipos:
            raise NotImplementedError(f'No hay esquema de integración para {nombre}')

        def campo(nombre_campo: str) -> str:
            return str(getattr(evento, nombre_campo, '') or '')

        return (
            EventoTrabajo(
                **self._sobre(evento, tipos[nombre]),
                trabajo_id=str(evento.trabajo_id),
                partner_id=campo('partner_id'),
                canal=campo('canal'),
                pais=campo('pais'),
                ciudad=campo('ciudad'),
                categoria=campo('categoria'),
                urgencia=campo('urgencia'),
                # En la creación es el estado inicial; en el cambio, el nuevo.
                estado=campo('estado') or campo('estado_nuevo'),
                estado_anterior=campo('estado_anterior'),
            ),
            EventoTrabajo,
        )

    def dto_a_entidad(self, dto):
        raise NotImplementedError
