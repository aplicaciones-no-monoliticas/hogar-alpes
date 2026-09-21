"""Comando CancelarVigenciaRechazada — compensación de la saga (D2 de
research.md) cuando Acreditación rechaza la vigencia del proveedor propuesto.
Idempotente ante reentrega, igual que el resto de los comandos de la saga.
"""
from dataclasses import dataclass

from gestion_trabajos.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from gestion_trabajos.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.objetos_valor import Estado
from ...dominio.repositorios import RepositorioTrabajos
from .base import TrabajoBaseHandler


@dataclass
class CancelarVigenciaRechazada(Comando):
    trabajo_id: str = ''


class CancelarVigenciaRechazadaHandler(TrabajoBaseHandler):
    def handle(self, comando: CancelarVigenciaRechazada):
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)
        trabajo = repositorio.obtener_por_id(comando.trabajo_id)

        if not trabajo or trabajo.estado.valor != Estado.EMPAREJANDO:
            return

        trabajo.cambiar_estado(Estado.CANCELADO)

        UnidadTrabajoPuerto.registrar_batch(repositorio.actualizar, trabajo)
        UnidadTrabajoPuerto.commit()


@ejecutar_comando.register(CancelarVigenciaRechazada)
def ejecutar_comando_cancelar_vigencia_rechazada(comando: CancelarVigenciaRechazada):
    return CancelarVigenciaRechazadaHandler().handle(comando)
