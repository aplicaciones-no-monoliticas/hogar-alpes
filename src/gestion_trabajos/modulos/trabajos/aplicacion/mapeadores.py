"""Mapeador de la capa de aplicación: DTO <-> agregación de dominio."""
import uuid

from gestion_trabajos.seedwork.aplicacion.dto import DTO
from gestion_trabajos.seedwork.dominio.repositorios import Mapeador

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
from .dto import SubTrabajoDTO, TrabajoDTO

URGENCIAS_MINUTOS = {'CRITICA': 60, 'ALTA': 240, 'NORMAL': 1440, 'BAJA': 4320}


class MapeadorTrabajoDTOJson(Mapeador):
    def obtener_tipo(self) -> type:
        return Trabajo

    def externo_a_dto(self, externo: dict) -> TrabajoDTO:
        return TrabajoDTO(
            canal=externo.get('canal', Canal.MARKETPLACE.value),
            partner_id=externo.get('partner_id', ''),
            referencia_externa=externo.get('referencia_externa', ''),
            categoria=externo.get('categoria', ''),
            urgencia=externo.get('urgencia', 'NORMAL'),
            pais=externo.get('pais', ''),
            ciudad=externo.get('ciudad', ''),
            direccion=externo.get('direccion', ''),
            descripcion=externo.get('descripcion', ''),
        )

    def dto_a_externo(self, dto: TrabajoDTO) -> dict:
        return {
            'id': dto.id,
            'fecha_creacion': dto.fecha_creacion,
            'fecha_actualizacion': dto.fecha_actualizacion,
            'canal': dto.canal,
            'partner_id': dto.partner_id,
            'referencia_externa': dto.referencia_externa,
            'categoria': dto.categoria,
            'urgencia': dto.urgencia,
            'ubicacion': {'pais': dto.pais, 'ciudad': dto.ciudad, 'direccion': dto.direccion},
            'descripcion': dto.descripcion,
            'estado': dto.estado,
            'sub_trabajos': [
                {'id': s.id, 'descripcion': s.descripcion, 'categoria': s.categoria, 'estado': s.estado}
                for s in dto.sub_trabajos
            ],
        }

    def entidad_a_dto(self, entidad: Trabajo) -> TrabajoDTO:
        return TrabajoDTO(
            id=str(entidad.id),
            fecha_creacion=entidad.fecha_creacion.isoformat(),
            fecha_actualizacion=entidad.fecha_actualizacion.isoformat(),
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
                SubTrabajoDTO(
                    id=str(s.id),
                    descripcion=s.descripcion,
                    categoria=s.categoria.codigo,
                    estado=s.estado.valor.value,
                )
                for s in entidad.sub_trabajos
            ],
        )

    def dto_a_entidad(self, dto: TrabajoDTO) -> Trabajo:
        trabajo = Trabajo(
            solicitante=Solicitante(
                canal=Canal(dto.canal),
                partner_id=dto.partner_id,
                referencia_externa=dto.referencia_externa,
            ),
            categoria=Categoria(codigo=dto.categoria),
            urgencia=Urgencia(
                nivel=dto.urgencia,
                minutos_objetivo=URGENCIAS_MINUTOS.get(dto.urgencia, 1440),
            ),
            ubicacion=Ubicacion(pais=dto.pais, ciudad=dto.ciudad, direccion=dto.direccion),
            descripcion=dto.descripcion,
        )
        if dto.id:
            trabajo.id = uuid.UUID(dto.id)
        if dto.estado:
            trabajo.estado = EstadoTrabajo(Estado(dto.estado))
        trabajo.sub_trabajos = [
            SubTrabajo(
                descripcion=s.descripcion,
                categoria=Categoria(codigo=s.categoria),
                estado=EstadoTrabajo(Estado(s.estado)) if s.estado else EstadoTrabajo(),
            )
            for s in dto.sub_trabajos
        ]
        return trabajo
