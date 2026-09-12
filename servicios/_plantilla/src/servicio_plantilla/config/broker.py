"""Conexión al broker: un cliente y un productor por proceso.

La primera versión de Gestión de Trabajos abría un cliente de Pulsar **por cada
mensaje** (brecha `G-3a`): con el volumen del escenario 8, el costo de conexión
se paga en cada evento. Aquí el cliente y los productores se crean una vez y se
reutilizan.

`BROKER_LISTENER` solo se usa desde el host. Los brokers anuncian su dirección
interna (`broker-N:6650`), que no resuelve fuera de la red de Docker; por eso
las herramientas que corren en la máquina del desarrollador piden el listener
`external`. Ver `docs/decisiones.md` · INF-2.
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
_candado = threading.Lock()


def url_broker() -> str:
    return os.getenv('BROKER_URL', f"pulsar://{os.getenv('BROKER_HOST', 'localhost')}:6650")


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
                # Configurable: las pruebas del reintento no pueden esperar 15 s
                # a que aflore el primer fallo.
                operation_timeout_seconds=int(os.getenv('BROKER_TIMEOUT', '15')),
            )
        return _cliente


def productor(topico: str, schema):
    """Un productor por (tópico, esquema), reutilizado durante toda la vida del proceso."""
    clave = (topico, schema.__name__)
    with _candado:
        if clave not in _productores:
            _productores[clave] = cliente().create_producer(
                topico, schema=AvroSchema(schema)
            )
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
