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
                try:
                    if app is not None:
                        with app.app_context():
                            manejar(mensaje.value(), mensaje)
                    else:
                        manejar(mensaje.value(), mensaje)
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
    """Emparejamiento tiene DOS suscripciones independientes: la regional a
    `evt-trabajo-{región}` (EMP-3) y la de proyección a `evt-acreditacion`
    (EMP-2). `ROL_CONSUMIDOR` decide cuál corre en este proceso:

    - `regional`   — solo `evt-trabajo-{región}`. Es la que escala el
      escenario 8 (`docker compose --scale`) sin arrastrar réplicas ociosas de
      la proyección.
    - `proyeccion` — solo `evt-acreditacion`.
    - `todos` (por defecto) — las dos, en hilos separados. Cómodo para
      desarrollo y para una demo de un solo contenedor por región.
    """
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(name)s | %(message)s',
    )
    import threading

    from . import crear_app
    from .modulos.emparejamiento.infraestructura.consumidores import (
        suscribirse_proyeccion,
        suscribirse_regional,
    )

    app = crear_app()
    rol = os.getenv('ROL_CONSUMIDOR', 'todos')

    hilos = []
    if rol in ('regional', 'todos'):
        hilos.append(threading.Thread(target=suscribirse_regional, args=(app,), daemon=True))
    if rol in ('proyeccion', 'todos'):
        hilos.append(threading.Thread(target=suscribirse_proyeccion, args=(app,), daemon=True))
    if not hilos:
        raise SystemExit(f'ROL_CONSUMIDOR desconocido: {rol!r}')

    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()


if __name__ == '__main__':
    main()
