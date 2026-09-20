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
- **propiedades** `partner_id` y `region`, legibles sin deserializar el
  mensaje. El `correlation_id` (`TO-4`) lo agrega el despachador desde el
  contexto de la petición: no pasa por aquí ni por el dominio.
"""
from pydispatch import dispatcher

from gestion_trabajos.config.topicos import region, topico_evt_trabajo
from gestion_trabajos.seedwork.aplicacion.handlers import Handler
from gestion_trabajos.seedwork.infraestructura import correlacion
from gestion_trabajos.seedwork.infraestructura.despachadores import Despachador

from ..infraestructura.mapeadores import MapeadorEventosTrabajo

def _propiedades(evento) -> dict:
    propiedades = {
        'partner_id': getattr(evento, 'partner_id', None),
        'region': region(getattr(evento, 'pais', None)),
    }
    # Marca de demostración de la saga (D3 de research.md): nunca es parte del
    # esquema Avro, solo viaja como propiedad, y solo si el productor la trajo.
    simular_fallo = getattr(evento, 'simular_fallo', '')
    if simular_fallo:
        propiedades['simular_fallo'] = simular_fallo
    return propiedades


def _publicar(evento):
    """Los dos tipos de evento van al MISMO stream regional, con `trabajo_id`
    como clave: así el cambio de estado nunca se adelanta a la creación dentro
    de un mismo trabajo (brecha G-2)."""
    # `POST /trabajos` genera el id dentro del comando: aquí es donde se conoce.
    correlacion.agregar_campos(trabajo_id=str(evento.trabajo_id))
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
