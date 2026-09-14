"""Handler de eventos de INTEGRACIÓN del módulo trabajos.

Escucha la señal que la UoW emite después del commit y despacha el evento al
broker. Es el único punto del módulo que conoce que existe un broker.

Un tópico por tipo de evento, siguiendo la convención `evt.trabajo.*` de la
vista funcional C&C (HDA-003). No es solo cosmético: Pulsar registra un esquema
por tópico, así que dos eventos con payload distinto en el mismo tópico se
rechazan con `IncompatibleSchema`.

**Esto cambia en GT-3**, que unifica los dos tópicos en `evt-trabajo-{región}`
para que el orden entre la creación y los cambios de estado quede garantizado
dentro de un mismo trabajo (brecha `G-2`).

Desde GT-2, cada evento viaja con:

- **clave de partición** `trabajo_id`: es lo que preserva el orden por trabajo
  cuando el tópico se particiona (escenario 8);
- **propiedades** `partner_id`, `region` y `correlation_id`, legibles sin
  deserializar el mensaje. La correlación mitiga `TO-4`: en un sistema
  distribuido, sin ella un incidente es inauditable.
"""
from pydispatch import dispatcher

from gestion_trabajos.config.topicos import region, topico_evt_trabajo
from gestion_trabajos.seedwork.aplicacion.handlers import Handler
from gestion_trabajos.seedwork.infraestructura.despachadores import Despachador

from ..infraestructura.mapeadores import MapeadorEventosTrabajo

def _propiedades(evento) -> dict:
    return {
        'partner_id': getattr(evento, 'partner_id', None),
        'region': region(getattr(evento, 'pais', None)),
        'correlation_id': str(getattr(evento, 'trabajo_id', '')),
    }


def _publicar(evento):
    """Los dos tipos de evento van al MISMO stream regional, con `trabajo_id`
    como clave: así el cambio de estado nunca se adelanta a la creación dentro
    de un mismo trabajo (brecha G-2)."""
    Despachador().publicar_evento(
        evento,
        topico_evt_trabajo(getattr(evento, 'pais', None)),
        MapeadorEventosTrabajo(),
        clave=str(evento.trabajo_id),
        propiedades=_propiedades(evento),
    )


class HandlerTrabajoIntegracion(Handler):
    @staticmethod
    def handle_trabajo_creado(evento):
        _publicar(evento)

    @staticmethod
    def handle_estado_cambiado(evento):
        _publicar(evento)


dispatcher.connect(
    HandlerTrabajoIntegracion.handle_trabajo_creado, signal='TrabajoCreadoIntegracion'
)
dispatcher.connect(
    HandlerTrabajoIntegracion.handle_estado_cambiado,
    signal='EstadoTrabajoCambiadoIntegracion',
)
