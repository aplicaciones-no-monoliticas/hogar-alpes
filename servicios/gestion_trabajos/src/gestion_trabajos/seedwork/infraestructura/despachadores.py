"""Adaptador de salida hacia el broker de eventos (Apache Pulsar).

Genérico a propósito: recibe el mapeador del módulo que publica, así el seedwork
no depende de ningún módulo de negocio.
"""
import logging

import pulsar
from pulsar.schema import AvroSchema

from gestion_trabajos.config.broker import broker_host

logger = logging.getLogger(__name__)


class Despachador:
    def _publicar_mensaje(self, mensaje, topico: str, schema):
        cliente = None
        try:
            cliente = pulsar.Client(f'pulsar://{broker_host()}:6650')
            publicador = cliente.create_producer(topico, schema=AvroSchema(schema))
            publicador.send(mensaje)
            logger.info('Evento publicado en %s', topico)
        except Exception as e:
            # El servicio no puede caerse porque el broker no esté disponible:
            # es el escenario 6 (la caída del reactor no degrada al productor).
            logger.warning('No se pudo publicar en %s: %s', topico, e)
        finally:
            if cliente:
                cliente.close()

    def publicar_evento(self, evento, topico: str, mapeador):
        mensaje, schema = mapeador.entidad_a_dto(evento)
        self._publicar_mensaje(mensaje, topico, schema)
