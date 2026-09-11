"""AQUÍ está la comunicación entre módulos por eventos de dominio.

`operaciones` se suscribe a las señales que emite la Unidad de Trabajo ANTES del
commit. No importa ni una línea del módulo `trabajos`: la señal es una cadena y
el evento se lee por atributos.

Consecuencia práctica: si `trabajos` agrega un estado nuevo al ciclo de vida
(escenario 3), este handler sigue funcionando sin cambios.
"""
import logging

from pydispatch import dispatcher

from gestion_trabajos.seedwork.aplicacion.handlers import Handler
from gestion_trabajos.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ..dominio.fabricas import FabricaSeguimientos
from ..dominio.repositorios import RepositorioSeguimientos
from ..infraestructura.fabricas import FabricaRepositorioSeguimientos

logger = logging.getLogger(__name__)


class HandlerSeguimientoDominio(Handler):
    @staticmethod
    def handle_trabajo_creado(evento):
        logger.info('[operaciones] TrabajoCreado recibido: %s', evento.trabajo_id)

        seguimiento = FabricaSeguimientos().crear_objeto(evento)
        repositorio = FabricaRepositorioSeguimientos().crear_objeto(RepositorioSeguimientos)
        # Se une a la MISMA unidad de trabajo: si el commit falla, no queda un
        # seguimiento huérfano de un trabajo que nunca se creó.
        UnidadTrabajoPuerto.registrar_batch(repositorio.agregar, seguimiento)

    @staticmethod
    def handle_estado_cambiado(evento):
        logger.info(
            '[operaciones] EstadoTrabajoCambiado: %s %s -> %s',
            evento.trabajo_id,
            evento.estado_anterior,
            evento.estado_nuevo,
        )
        repositorio = FabricaRepositorioSeguimientos().crear_objeto(RepositorioSeguimientos)
        seguimiento = repositorio.obtener_por_trabajo(str(evento.trabajo_id))
        if not seguimiento:
            return
        seguimiento.registrar_cambio_estado(evento.estado_nuevo)
        UnidadTrabajoPuerto.registrar_batch(repositorio.actualizar, seguimiento)


dispatcher.connect(
    HandlerSeguimientoDominio.handle_trabajo_creado, signal='TrabajoCreadoDominio'
)
dispatcher.connect(
    HandlerSeguimientoDominio.handle_estado_cambiado,
    signal='EstadoTrabajoCambiadoDominio',
)
