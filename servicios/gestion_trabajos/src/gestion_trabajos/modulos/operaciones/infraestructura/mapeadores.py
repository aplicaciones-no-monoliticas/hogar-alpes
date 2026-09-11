import uuid

from gestion_trabajos.seedwork.dominio.repositorios import Mapeador

from ..dominio.entidades import SeguimientoOperativo
from ..dominio.objetos_valor import Prioridad, VentanaSLA
from . import dto as modelo


class MapeadorSeguimiento(Mapeador):
    def obtener_tipo(self) -> type:
        return SeguimientoOperativo

    def entidad_a_dto(self, entidad: SeguimientoOperativo) -> modelo.Seguimiento:
        return modelo.Seguimiento(
            id=str(entidad.id),
            trabajo_id=entidad.trabajo_id,
            pais=entidad.pais,
            canal=entidad.canal,
            categoria=entidad.categoria,
            estado_trabajo=entidad.estado_trabajo,
            prioridad=entidad.ventana_sla.prioridad.value,
            minutos_sla=entidad.ventana_sla.minutos,
            fecha_creacion=entidad.fecha_creacion,
            fecha_actualizacion=entidad.fecha_actualizacion,
        )

    def dto_a_entidad(self, dto: modelo.Seguimiento) -> SeguimientoOperativo:
        return SeguimientoOperativo(
            id=uuid.UUID(dto.id),
            fecha_creacion=dto.fecha_creacion,
            fecha_actualizacion=dto.fecha_actualizacion,
            trabajo_id=dto.trabajo_id,
            pais=dto.pais,
            canal=dto.canal,
            categoria=dto.categoria,
            estado_trabajo=dto.estado_trabajo,
            ventana_sla=VentanaSLA(
                minutos=dto.minutos_sla, prioridad=Prioridad(dto.prioridad)
            ),
        )
