"""Comando CambiarEstadoTrabajo.

Sustenta el escenario 3: agregar un estado nuevo al ciclo de vida se resuelve
en el objeto valor `EstadoTrabajo`; ni este handler ni los consumidores externos
cambian.
"""
from dataclasses import dataclass

from gestion_trabajos.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from gestion_trabajos.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.objetos_valor import Estado
from ...dominio.repositorios import RepositorioTrabajos
from .base import TrabajoBaseHandler


@dataclass
class CambiarEstadoTrabajo(Comando):
    trabajo_id: str = ''
    estado: str = ''


class CambiarEstadoTrabajoHandler(TrabajoBaseHandler):
    def handle(self, comando: CambiarEstadoTrabajo):
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)
        trabajo = repositorio.obtener_por_id(comando.trabajo_id)

        if not trabajo:
            raise ValueError(f'No existe el trabajo {comando.trabajo_id}')

        trabajo.cambiar_estado(Estado(comando.estado))

        UnidadTrabajoPuerto.registrar_batch(repositorio.actualizar, trabajo)
        UnidadTrabajoPuerto.commit()

        return str(trabajo.id)


@ejecutar_comando.register(CambiarEstadoTrabajo)
def ejecutar_comando_cambiar_estado(comando: CambiarEstadoTrabajo):
    return CambiarEstadoTrabajoHandler().handle(comando)
