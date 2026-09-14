"""Comando RegistrarCambioEstado — interno, traducido desde
`EstadoTrabajoCambiado` en `evt-trabajo-.*` (OPS-2).

**No descarta en silencio** (corrige G-2/G-1, CA-6.5): si el cambio de estado
llega para un `trabajo_id` sin seguimiento abierto —por ejemplo, tras una
caída que superó la ventana de retención, o si el `TrabajoCreado` sigue en
camino y llegan desordenados entre particiones— se registra como HUERFANO en
`eventos_procesados` en lugar de perderse. Sigue siendo contable para CA-6.5.
"""
from dataclasses import dataclass

from operaciones.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from operaciones.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.repositorios import RepositorioEventosProcesados, RepositorioSeguimientos
from .base import OperacionesBaseHandler

TIPO = 'EstadoTrabajoCambiado'


@dataclass
class RegistrarCambioEstado(Comando):
    evento_id: str = ''
    trabajo_id: str = ''
    estado_nuevo: str = ''
    estado_anterior: str = ''


class RegistrarCambioEstadoHandler(OperacionesBaseHandler):
    def handle(self, comando: RegistrarCambioEstado) -> str:
        repo_eventos = self.fabrica_repositorio.crear_objeto(RepositorioEventosProcesados)
        if repo_eventos.ya_procesado(comando.evento_id):
            return 'DUPLICADO'

        repo_seguimientos = self.fabrica_repositorio.crear_objeto(RepositorioSeguimientos)
        seguimiento = repo_seguimientos.obtener_por_trabajo(comando.trabajo_id)

        if not seguimiento:
            UnidadTrabajoPuerto.registrar_batch(
                repo_eventos.registrar, comando.evento_id, TIPO, 'HUERFANO'
            )
            UnidadTrabajoPuerto.commit()
            return 'HUERFANO'

        seguimiento.registrar_cambio_estado(comando.estado_nuevo)
        UnidadTrabajoPuerto.registrar_batch(repo_seguimientos.actualizar, seguimiento)
        UnidadTrabajoPuerto.registrar_batch(
            repo_eventos.registrar, comando.evento_id, TIPO, 'APLICADO'
        )
        UnidadTrabajoPuerto.commit()
        return 'APLICADO'


@ejecutar_comando.register(RegistrarCambioEstado)
def ejecutar_comando_registrar_cambio_estado(comando: RegistrarCambioEstado):
    return RegistrarCambioEstadoHandler().handle(comando)
