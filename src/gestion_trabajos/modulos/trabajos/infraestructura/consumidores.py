"""ADAPTADOR de entrada asíncrono: consume comandos del tópico `cmd-trabajo`.

Es la ruta que sustenta el escenario 7: el Gateway publica el comando y el
servicio lo drena a su ritmo, sin que el productor espere.
"""
import logging
import time

import pulsar
from pulsar.schema import AvroSchema

from gestion_trabajos.config.broker import broker_host

from .schema.v1.comandos import ComandoCrearTrabajo

logger = logging.getLogger(__name__)
TOPICO_COMANDOS_TRABAJO = 'cmd-trabajo'


def suscribirse_a_comandos(app=None):
    cliente = None
    try:
        cliente = pulsar.Client(f'pulsar://{broker_host()}:6650')
        consumidor = cliente.subscribe(
            TOPICO_COMANDOS_TRABAJO,
            consumer_type=pulsar.ConsumerType.Shared,
            subscription_name='gestion-trabajos-sub-comandos',
            schema=AvroSchema(ComandoCrearTrabajo),
        )

        while True:
            mensaje = consumidor.receive()
            datos = mensaje.value().data
            logger.info('Comando recibido: %s', datos)

            from ..aplicacion.comandos.crear_trabajo import CrearTrabajo
            from gestion_trabajos.seedwork.aplicacion.comandos import ejecutar_comando

            comando = CrearTrabajo(
                canal=datos.canal,
                partner_id=datos.partner_id,
                referencia_externa=datos.referencia_externa,
                categoria=datos.categoria,
                urgencia=datos.urgencia,
                pais=datos.pais,
                ciudad=datos.ciudad,
                direccion=datos.direccion,
                descripcion=datos.descripcion,
            )
            if app:
                with app.app_context():
                    ejecutar_comando(comando)
            else:
                ejecutar_comando(comando)

            consumidor.acknowledge(mensaje)
    except Exception:
        logger.exception('Error suscribiéndose al tópico de comandos')
    finally:
        if cliente:
            cliente.close()
