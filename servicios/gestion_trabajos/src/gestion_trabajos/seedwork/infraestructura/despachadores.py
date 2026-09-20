"""Adaptador de salida hacia el broker de eventos (Apache Pulsar).

Genérico a propósito: recibe el mapeador del módulo que publica, así el seedwork
no depende de ningún módulo de negocio.

Tres diferencias con la versión anterior:

1. **Reutiliza el productor** (brecha `G-3a`). Antes abría un cliente de Pulsar
   por mensaje.
2. **Acepta clave de partición y propiedades.** La clave es lo que garantiza el
   orden dentro de un mismo `trabajoId` (escenario 8); las propiedades llevan
   `partner_id`, `region` y el identificador de correlación sin obligar a
   deserializar el mensaje (`TO-4`).
3. Si el broker falla, registra el error y **no tumba la transacción de
   negocio**: el commit ya ocurrió. La contrapartida es que ese evento se pierde
   —riesgo `R-3`, cuya solución es el patrón *outbox* y está fuera del alcance
   de esta entrega—.
"""
import logging

from gestion_trabajos.config.broker import productor

from . import correlacion

logger = logging.getLogger(__name__)


class Despachador:
    def publicar_evento(self, evento, topico: str, mapeador, clave: str | None = None,
                        propiedades: dict | None = None):
        mensaje, schema = mapeador.entidad_a_dto(evento)
        self._publicar_mensaje(mensaje, topico, schema, clave, propiedades)

    def _publicar_mensaje(self, mensaje, topico: str, schema, clave: str | None = None,
                          propiedades: dict | None = None):
        # La correlación sale del contexto de borde y pisa lo que haya puesto el handler.
        # No es la clave de partición: esa sigue viajando aparte, en `partition_key`.
        properties = {k: str(v) for k, v in (propiedades or {}).items() if v is not None}
        properties['correlation_id'] = correlacion.actual()
        try:
            productor(topico, schema).send(
                mensaje,
                partition_key=str(clave) if clave else None,
                properties=properties,
            )
            logger.info('Evento publicado en %s (clave=%s)', topico, clave)
        except Exception as e:
            # El servicio no puede caerse porque el broker no esté disponible:
            # la caída del reactor no degrada al productor (escenario 6).
            logger.warning('No se pudo publicar en %s: %s', topico, e)
