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
import os

from pydispatch import dispatcher

from gestion_trabajos.seedwork.aplicacion.handlers import Handler
from gestion_trabajos.seedwork.infraestructura.despachadores import Despachador

from ..infraestructura.mapeadores import MapeadorEventosTrabajo

TOPICO_TRABAJO_CREADO = 'evt-trabajo-creado'
TOPICO_TRABAJO_ESTADO = 'evt-trabajo-estado'

# País -> región. Es configuración, no código: abrir un país no obliga a tocar
# este archivo. GT-3 lo mueve a `infra/regiones.json`.
REGIONES = {'CO': 'andina', 'MX': 'norteamerica', 'BR': 'conosur', 'AR': 'conosur'}
REGION_POR_DEFECTO = os.getenv('REGION_POR_DEFECTO', 'andina')


def _region(pais: str | None) -> str:
    return REGIONES.get((pais or '').upper(), REGION_POR_DEFECTO)


def _propiedades(evento) -> dict:
    return {
        'partner_id': getattr(evento, 'partner_id', None),
        'region': _region(getattr(evento, 'pais', None)),
        'correlation_id': str(getattr(evento, 'trabajo_id', '')),
    }


class HandlerTrabajoIntegracion(Handler):
    @staticmethod
    def handle_trabajo_creado(evento):
        Despachador().publicar_evento(
            evento,
            TOPICO_TRABAJO_CREADO,
            MapeadorEventosTrabajo(),
            clave=str(evento.trabajo_id),
            propiedades=_propiedades(evento),
        )

    @staticmethod
    def handle_estado_cambiado(evento):
        Despachador().publicar_evento(
            evento,
            TOPICO_TRABAJO_ESTADO,
            MapeadorEventosTrabajo(),
            clave=str(evento.trabajo_id),
            propiedades=_propiedades(evento),
        )


dispatcher.connect(
    HandlerTrabajoIntegracion.handle_trabajo_creado, signal='TrabajoCreadoIntegracion'
)
dispatcher.connect(
    HandlerTrabajoIntegracion.handle_estado_cambiado,
    signal='EstadoTrabajoCambiadoIntegracion',
)
