"""Handler de eventos de INTEGRACIÓN del módulo trabajos.

Escucha la señal que la UoW emite después del commit y despacha el evento al
broker. Es el único punto del módulo que conoce que existe un broker.

Un tópico por tipo de evento, siguiendo la convención `evt.trabajo.*` de la
vista funcional C&C (HDA-003). No es solo cosmético: Pulsar registra un esquema
por tópico, así que dos eventos con payload distinto en el mismo tópico se
rechazan con `IncompatibleSchema`. Separarlos también deja que cada consumidor
se suscriba solo a lo que le interesa.
"""
from pydispatch import dispatcher

from gestion_trabajos.seedwork.aplicacion.handlers import Handler
from gestion_trabajos.seedwork.infraestructura.despachadores import Despachador

from ..infraestructura.mapeadores import MapeadorEventosTrabajo

TOPICO_TRABAJO_CREADO = 'evt-trabajo-creado'
TOPICO_TRABAJO_ESTADO = 'evt-trabajo-estado'


class HandlerTrabajoIntegracion(Handler):
    @staticmethod
    def handle_trabajo_creado(evento):
        Despachador().publicar_evento(
            evento, TOPICO_TRABAJO_CREADO, MapeadorEventosTrabajo()
        )

    @staticmethod
    def handle_estado_cambiado(evento):
        Despachador().publicar_evento(
            evento, TOPICO_TRABAJO_ESTADO, MapeadorEventosTrabajo()
        )


dispatcher.connect(
    HandlerTrabajoIntegracion.handle_trabajo_creado, signal='TrabajoCreadoIntegracion'
)
dispatcher.connect(
    HandlerTrabajoIntegracion.handle_estado_cambiado,
    signal='EstadoTrabajoCambiadoIntegracion',
)
