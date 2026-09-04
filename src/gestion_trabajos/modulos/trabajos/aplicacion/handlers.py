"""Handler de eventos de INTEGRACIÓN del módulo trabajos.

Escucha la señal que la UoW emite después del commit y despacha el evento al
broker. Es el único punto del módulo que conoce que existe un broker.
"""
from pydispatch import dispatcher

from gestion_trabajos.seedwork.aplicacion.handlers import Handler
from gestion_trabajos.seedwork.infraestructura.despachadores import Despachador
from ..infraestructura.mapeadores import MapeadorEventosTrabajo

TOPICO_EVENTOS_TRABAJO = 'evt-trabajo'


class HandlerTrabajoIntegracion(Handler):
    @staticmethod
    def handle_trabajo_creado(evento):
        Despachador().publicar_evento(evento, TOPICO_EVENTOS_TRABAJO, MapeadorEventosTrabajo())

    @staticmethod
    def handle_estado_cambiado(evento):
        Despachador().publicar_evento(evento, TOPICO_EVENTOS_TRABAJO, MapeadorEventosTrabajo())


dispatcher.connect(
    HandlerTrabajoIntegracion.handle_trabajo_creado, signal='TrabajoCreadoIntegracion'
)
dispatcher.connect(
    HandlerTrabajoIntegracion.handle_estado_cambiado,
    signal='EstadoTrabajoCambiadoIntegracion',
)
