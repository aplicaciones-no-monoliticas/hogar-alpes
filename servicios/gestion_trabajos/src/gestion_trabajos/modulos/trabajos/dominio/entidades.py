"""Agregación Trabajo.

Decisión congelada aquí (PS-9 de la Entrega 2): `SubTrabajo` vive DENTRO del
límite de `Trabajo`. La consecuencia aceptada es que cada actualización de un
sub-trabajo toma el bloqueo de la raíz. La alternativa —promover SubTrabajo a
raíz propia— gana concurrencia y pierde consistencia inmediata dentro del
trabajo. Es la decisión de modelado más cara de revertir del proyecto.
"""
import uuid
from dataclasses import dataclass, field

from gestion_trabajos.seedwork.dominio.entidades import AgregacionRaiz, Entidad
from gestion_trabajos.seedwork.dominio.mixins import ValidarReglasMixin

from .eventos import EstadoTrabajoCambiado, SubTrabajoAgregado, TrabajoCreado
from .objetos_valor import (
    Categoria,
    Estado,
    EstadoTrabajo,
    Solicitante,
    Ubicacion,
    Urgencia,
)
from .reglas import (
    CategoriaPermitidaEnRegion,
    TransicionDeEstadoValida,
    UbicacionCompleta,
    UrgenciaPermitidaEnRegion,
)


@dataclass
class SubTrabajo(Entidad):
    """Entidad interna del agregado: tiene identidad, pero no se accede sin
    pasar por la raíz."""
    descripcion: str = ''
    categoria: Categoria = field(default_factory=Categoria)
    estado: EstadoTrabajo = field(default_factory=EstadoTrabajo)

    def cambiar_estado(self, destino: Estado):
        self.estado = EstadoTrabajo(destino)


@dataclass
class Trabajo(AgregacionRaiz, ValidarReglasMixin):
    solicitante: Solicitante = field(default_factory=Solicitante)
    categoria: Categoria = field(default_factory=Categoria)
    urgencia: Urgencia = field(default_factory=Urgencia)
    ubicacion: Ubicacion = field(default_factory=Ubicacion)
    descripcion: str = ''
    estado: EstadoTrabajo = field(default_factory=EstadoTrabajo)
    sub_trabajos: list[SubTrabajo] = field(default_factory=list)

    def crear(self, categorias_permitidas: list[str], urgencias_permitidas: list[str]):
        """Las listas permitidas llegan del sidecar regional a través del handler.
        El dominio valida contra ellas sin saber de qué país vinieron."""
        self.validar_regla(UbicacionCompleta(self.ubicacion))
        self.validar_regla(CategoriaPermitidaEnRegion(self.categoria, categorias_permitidas))
        self.validar_regla(UrgenciaPermitidaEnRegion(self.urgencia, urgencias_permitidas))

        self.estado = EstadoTrabajo(Estado.CREADO)
        self.agregar_evento(
            TrabajoCreado(
                trabajo_id=self.id,
                categoria=self.categoria.codigo,
                urgencia=self.urgencia.nivel,
                pais=self.ubicacion.pais,
                ciudad=self.ubicacion.ciudad,
                canal=self.solicitante.canal.value,
                partner_id=self.solicitante.partner_id,
                estado=self.estado.valor.value,
            )
        )

    def cambiar_estado(self, destino: Estado):
        self.validar_regla(TransicionDeEstadoValida(self.estado, destino))
        anterior = self.estado.valor
        self.estado = EstadoTrabajo(destino)
        self.agregar_evento(
            EstadoTrabajoCambiado(
                trabajo_id=self.id,
                estado_anterior=anterior.value,
                estado_nuevo=destino.value,
            )
        )

    def agregar_sub_trabajo(self, sub_trabajo: SubTrabajo):
        self.sub_trabajos.append(sub_trabajo)
        self.agregar_evento(
            SubTrabajoAgregado(
                trabajo_id=self.id,
                sub_trabajo_id=sub_trabajo.id,
                categoria=sub_trabajo.categoria.codigo,
            )
        )
