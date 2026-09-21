"""Comando CancelarSinCandidatos — compensación directa (D2 de research.md):
Emparejamiento nunca llegó a reservar nada, así que no hay nada que liberar del
lado de GT. Idempotente ante reentrega, igual que `ConfirmarAsignacion`.
"""
from dataclasses import dataclass

from gestion_trabajos.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from gestion_trabajos.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.objetos_valor import Estado
from ...dominio.repositorios import RepositorioTrabajos
from .base import TrabajoBaseHandler


@dataclass
class CancelarSinCandidatos(Comando):
    trabajo_id: str = ''


class CancelarSinCandidatosHandler(TrabajoBaseHandler):
    def handle(self, comando: CancelarSinCandidatos):
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)
        trabajo = repositorio.obtener_por_id(comando.trabajo_id)

        if not trabajo or trabajo.estado.valor != Estado.EMPAREJANDO:
            return

        trabajo.cambiar_estado(Estado.CANCELADO)

        UnidadTrabajoPuerto.registrar_batch(repositorio.actualizar, trabajo)
        UnidadTrabajoPuerto.commit()


@ejecutar_comando.register(CancelarSinCandidatos)
def ejecutar_comando_cancelar_sin_candidatos(comando: CancelarSinCandidatos):
    return CancelarSinCandidatosHandler().handle(comando)
