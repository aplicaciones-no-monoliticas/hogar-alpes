"""Conexión al broker: un cliente y un productor por proceso.

Antes se abría un cliente de Pulsar **por cada mensaje** (brecha `G-3a`): con el
volumen del escenario 8, el costo de conexión se paga en cada evento. Aquí el
cliente y los productores se crean una vez y se reutilizan durante toda la vida
del proceso.

Es el mismo código que la plantilla de servicio. Ese es el costo de `TO-7`: el
arreglo se hace una vez en la plantilla y otra vez aquí.

`BROKER_LISTENER` solo se usa desde el host: los brokers anuncian su dirección
interna (`broker-N:6650`), que no resuelve fuera de la red de Docker.
"""
import atexit
import logging
import os
import threading

import pulsar
from pulsar.schema import AvroSchema

logger = logging.getLogger(__name__)

_cliente: pulsar.Client | None = None
_productores: dict = {}
# Reentrante a propósito: `productor()` toma el candado y llama a `cliente()`,
# que vuelve a tomarlo. Con un Lock normal, la PRIMERA publicación se
# autobloquea y la petición HTTP se cuelga para siempre, sin un solo mensaje de
# error. Ver docs/decisiones.md · GT-2.
_candado = threading.RLock()


def broker_host() -> str:
    return os.getenv('BROKER_HOST', 'localhost')


def url_broker() -> str:
    return os.getenv('BROKER_URL', f'pulsar://{broker_host()}:6650')


def listener() -> str | None:
    return os.getenv('BROKER_LISTENER') or None


def cliente() -> pulsar.Client:
    global _cliente
    with _candado:
        if _cliente is None:
            logger.info('Conectando al broker %s (listener=%s)', url_broker(), listener())
            _cliente = pulsar.Client(
                url_broker(),
                listener_name=listener(),
                operation_timeout_seconds=int(os.getenv('BROKER_TIMEOUT', '15')),
            )
        return _cliente


def productor(topico: str, schema):
    """Un productor por (tópico, esquema), reutilizado por el proceso."""
    clave = (topico, schema.__name__)
    with _candado:
        if clave not in _productores:
            _productores[clave] = cliente().create_producer(topico, schema=AvroSchema(schema))
        return _productores[clave]


def cerrar():
    global _cliente
    with _candado:
        for p in _productores.values():
            try:
                p.close()
            except Exception:
                pass
        _productores.clear()
        if _cliente is not None:
            try:
                _cliente.close()
            except Exception:
                pass
            _cliente = None


atexit.register(cerrar)
