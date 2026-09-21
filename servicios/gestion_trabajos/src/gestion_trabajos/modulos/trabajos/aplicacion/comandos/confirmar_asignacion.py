"""Comando ConfirmarAsignacion — paso 4 de ida de la saga (D2/D5 de research.md),
para `vigencia-confirmada`. Idempotente ante reentrega: si el trabajo ya no
está en `EMPAREJANDO`, es un no-op — la transición ya ocurrió.
"""
from dataclasses import dataclass

from gestion_trabajos.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from gestion_trabajos.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.objetos_valor import Estado
from ...dominio.repositorios import RepositorioTrabajos
from .base import TrabajoBaseHandler


@dataclass
class ConfirmarAsignacion(Comando):
    trabajo_id: str = ''
    proveedor_id: str = ''
    # Marca de demostración de la saga (D3 de research.md): si es 'ASIGNACION'
    # (T040), la vigencia se confirmó pero la asignación final falla igual.
    simular_fallo: str = ''


class ConfirmarAsignacionHandler(TrabajoBaseHandler):
    def handle(self, comando: ConfirmarAsignacion):
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)
        trabajo = repositorio.obtener_por_id(comando.trabajo_id)

        if not trabajo or trabajo.estado.valor != Estado.EMPAREJANDO:
            # No existe, o la reentrega llega después de que ya se resolvió.
            return

        if comando.simular_fallo == 'ASIGNACION':
            trabajo.cambiar_estado(Estado.CANCELADO)
        else:
            trabajo.proveedor_id = comando.proveedor_id
            trabajo.cambiar_estado(Estado.ASIGNADO)

        UnidadTrabajoPuerto.registrar_batch(repositorio.actualizar, trabajo)
        UnidadTrabajoPuerto.commit()


@ejecutar_comando.register(ConfirmarAsignacion)
def ejecutar_comando_confirmar_asignacion(comando: ConfirmarAsignacion):
    return ConfirmarAsignacionHandler().handle(comando)
