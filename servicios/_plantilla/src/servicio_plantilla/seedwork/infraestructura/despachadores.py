"""Adaptador de salida hacia el broker de eventos.

Genérico a propósito: recibe el mapeador del módulo que publica, así el seedwork
no depende de ningún módulo de negocio.

Tres diferencias con la primera versión de Gestión de Trabajos:

1. **Reutiliza el productor** (brecha `G-3a`). Abrir un cliente por mensaje paga
   el costo de conexión en cada evento, y el escenario 8 multiplica el volumen.
2. **Acepta clave de partición y propiedades.** La clave es lo que garantiza el
   orden dentro de un mismo `trabajoId` (escenario 8); las propiedades llevan
   `partner_id`, `region` y el identificador de correlación sin obligar a
   deserializar el mensaje.
3. Si el broker falla, registra el error y **no tumba la transacción de
   negocio**: el commit ya ocurrió. La contrapartida es que ese evento se pierde
   —riesgo `R-3` de la especificación, cuya solución es el patrón *outbox* y
   está fuera del alcance de esta entrega—.
"""
import logging

from ...config.broker import productor

logger = logging.getLogger(__name__)


class Despachador:
    def publicar_evento(self, evento, topico: str, mapeador, clave: str | None = None,
                        propiedades: dict | None = None):
        mensaje, schema = mapeador.entidad_a_dto(evento)
        self._publicar_mensaje(mensaje, topico, schema, clave, propiedades)

    def _publicar_mensaje(self, mensaje, topico: str, schema, clave: str | None = None,
                          propiedades: dict | None = None):
        try:
            productor(topico, schema).send(
                mensaje,
                partition_key=str(clave) if clave else None,
                properties={k: str(v) for k, v in (propiedades or {}).items() if v is not None},
            )
            logger.info('Publicado en %s (clave=%s)', topico, clave)
        except Exception as e:
            logger.warning('No se pudo publicar en %s: %s', topico, e)
