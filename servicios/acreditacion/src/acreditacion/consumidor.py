"""Proceso consumidor: la mitad asíncrona del servicio.

Corre como proceso propio (`MODO=consumidor`), no como hilo dentro de la API.
Así se escala sin chocar con el puerto HTTP —escenario 8— y se puede detener el
reactor sin tumbar su API —escenario 6—.

**Reintenta la suscripción.** En la primera versión de Gestión de Trabajos, un
`TopicNotFound` al arrancar mataba el hilo para siempre y el servicio seguía
respondiendo `202` sin consumir nada, sin que nadie se enterara (INF-2 en
`docs/decisiones.md`). Aquí un fallo al suscribirse espera y vuelve a intentar.
"""
import logging
import os
import time

import pulsar
from pulsar.schema import AvroSchema

from .config.broker import cliente
from .seedwork.infraestructura import correlacion

logger = logging.getLogger(__name__)

ESPERA_REINTENTO = int(os.getenv('ESPERA_REINTENTO', '5'))


def correr(
    topicos,
    suscripcion: str,
    schema,
    manejar,
    tipo=pulsar.ConsumerType.Failover,
    app=None,
):
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


def main():
    """Acreditación tiene dos suscripciones: `cmd-acreditacion` (Failover, el
    ciclo de vida del agregado) y, desde la Entrega 5, `acreditacion` sobre
    `evt-emparejamiento` (Shared, D6 de research.md — confirmar/rechazar
    vigencia). Van en hilos separados, igual que en Emparejamiento."""
    correlacion.instalar_registro()
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(name)s | cid=%(correlation_id)s%(campos)s | %(message)s',
    )
    import threading

    from . import crear_app
    from .modulos.acreditacion.infraestructura.consumidores import suscribirse, suscribirse_saga

    app = crear_app()
    hilos = [
        threading.Thread(target=suscribirse, args=(app,), daemon=True),
        threading.Thread(target=suscribirse_saga, args=(app,), daemon=True),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()


if __name__ == '__main__':
    main()
