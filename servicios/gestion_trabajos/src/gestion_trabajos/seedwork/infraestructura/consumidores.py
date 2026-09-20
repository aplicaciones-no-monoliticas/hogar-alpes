"""Bucle de consumo genérico, con reintento.

La versión anterior atrapaba la excepción **fuera** del bucle: un
`TopicNotFound` al arrancar terminaba el hilo para siempre y el servicio seguía
respondiendo `202` sin consumir nada, sin que nadie se enterara. Es el defecto
que encontramos al levantar el clúster (INF-2 en `docs/decisiones.md`).

Aquí un fallo de suscripción espera y vuelve a intentar, y un fallo del handler
devuelve el mensaje al broker en lugar de perderlo.

Es el mismo código que la plantilla de servicio: el costo de `TO-7`.
"""
import logging
import os
import time

import pulsar
from pulsar.schema import AvroSchema

from gestion_trabajos.config.broker import cliente

from . import correlacion

logger = logging.getLogger(__name__)

ESPERA_REINTENTO = int(os.getenv('ESPERA_REINTENTO', '5'))


def correr(topicos, suscripcion: str, schema, manejar, tipo=pulsar.ConsumerType.Failover,
           app=None):
    """Consume `topicos` y entrega cada mensaje a `manejar(valor, mensaje)`.

    - Confirma (`ack`) **después** de que el handler terminó: si el proceso muere
      a mitad, el mensaje se reentrega. Es entrega al-menos-una-vez, así que el
      handler debe ser idempotente.
    - Ante una excepción del handler, `negative_acknowledge` para que Pulsar lo
      reentregue en lugar de perderlo.
    """
    while True:
        consumidor = None
        try:
            consumidor = cliente().subscribe(
                topicos,
                subscription_name=suscripcion,
                consumer_type=tipo,
                schema=AvroSchema(schema),
                initial_position=pulsar.InitialPosition.Earliest,
            )
            logger.info('Suscrito a %s como %s', topicos, suscripcion)

            while True:
                mensaje = consumidor.receive()
                valor, error_de_decodificacion = None, None
                try:
                    valor = mensaje.value()
                except Exception as error:
                    error_de_decodificacion = error
                # Todo lo que sigue —el handler, el error y el rechazo— ocurre dentro del
                # contexto de correlación del mensaje, para que cada línea lleve su `cid`.
                with correlacion.contexto(correlacion.desde_mensaje(valor, mensaje)):
                    try:
                        if error_de_decodificacion is not None:
                            raise error_de_decodificacion
                        if app is not None:
                            with app.app_context():
                                manejar(valor, mensaje)
                        else:
                            manejar(valor, mensaje)
                        consumidor.acknowledge(mensaje)
                    except Exception:
                        logger.exception('Error procesando el mensaje; se reentregará')
                        consumidor.negative_acknowledge(mensaje)

        except Exception:
            logger.exception(
                'Fallo en la suscripción a %s; reintentando en %ss', topicos, ESPERA_REINTENTO
            )
            if consumidor is not None:
                try:
                    consumidor.close()
                except Exception:
                    pass
            time.sleep(ESPERA_REINTENTO)
