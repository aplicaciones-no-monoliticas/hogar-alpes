"""El único consumidor de Operaciones (§4.2, §8 del plan técnico) — la capa
anticorrupción que reemplaza al handler de señales `pydispatch` que existía
cuando `operaciones` era un módulo del mismo proceso que `gestion_trabajos`
(G-1, OPS-2).

Suscripción durable `operaciones`, Failover, por PATRÓN `evt-trabajo-.*`:
todas las regiones, un único cursor. Por cada mensaje:

  1. traduce `TrabajoCreado` -> `AbrirSeguimiento` o
     `EstadoTrabajoCambiado` -> `RegistrarCambioEstado`;
  2. el comando se ejecuta en SU PROPIA Unidad de Trabajo (la de `operaciones`,
     no la de `gestion_trabajos`);
  3. `correr()` (en `operaciones.consumidor`) confirma (`ack`) el mensaje
     DESPUÉS de que el comando hizo commit, y lo reentrega (`nack`) si algo
     lanzó una excepción.

La deduplicación por `evento_id` vive dentro de cada comando (OPS-3), no aquí:
así un `AbrirSeguimiento` y un `RegistrarCambioEstado` comparten exactamente la
misma tabla `eventos_procesados` sin que este módulo tenga que decidir cuál
handler llamar dos veces.
"""
import logging

from operaciones.config.topicos import SUSCRIPCION, patron_evt_trabajo
from operaciones.seedwork.aplicacion.comandos import ejecutar_comando

from .schema.v1.evt_trabajo import TIPO_CREADO, TIPO_ESTADO_CAMBIADO, EventoTrabajo

logger = logging.getLogger(__name__)


def manejar_evento_trabajo(valor, mensaje):
    from ..aplicacion.comandos.abrir_seguimiento import AbrirSeguimiento
    from ..aplicacion.comandos.registrar_cambio_estado import RegistrarCambioEstado

    if valor.type == TIPO_CREADO:
        resultado = ejecutar_comando(AbrirSeguimiento(
            evento_id=valor.id,
            trabajo_id=valor.trabajo_id,
            pais=valor.pais,
            canal=valor.canal,
            categoria=valor.categoria,
            estado=valor.estado,
            urgencia=valor.urgencia,
        ))
    elif valor.type == TIPO_ESTADO_CAMBIADO:
        resultado = ejecutar_comando(RegistrarCambioEstado(
            evento_id=valor.id,
            trabajo_id=valor.trabajo_id,
            estado_nuevo=valor.estado,
            estado_anterior=valor.estado_anterior,
        ))
    else:
        logger.warning('evt-trabajo con type desconocido, se ignora: %s', valor.type)
        return

    logger.info('[operaciones] %s trabajo_id=%s -> %s', valor.type, valor.trabajo_id, resultado)


def suscribirse(app):
    import re

    from operaciones.consumidor import correr

    correr(
        re.compile(patron_evt_trabajo()),
        SUSCRIPCION,
        EventoTrabajo,
        manejar_evento_trabajo,
        app=app,
    )
