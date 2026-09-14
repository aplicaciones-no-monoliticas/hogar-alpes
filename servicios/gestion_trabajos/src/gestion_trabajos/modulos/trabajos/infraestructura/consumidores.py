"""ADAPTADOR de entrada asíncrono: consume comandos del tópico `cmd-trabajo`.

Es la ruta que sustenta el escenario 7 y la base del 8: el Gateway publica el
comando y el servicio lo drena a su ritmo, sin que el productor espere.

El bucle con reintento vive en el seedwork; aquí solo se declara **qué** se
consume y **cómo se traduce** el mensaje a un comando de aplicación. Esa
traducción es la capa anticorrupción: el contrato público entra, el modelo
interno sale.
"""
import logging

import pulsar

from gestion_trabajos.config.topicos import SUSCRIPCION_COMANDOS, patron_cmd_trabajo
from gestion_trabajos.seedwork.infraestructura.consumidores import correr

from .schema.v1.comandos import ComandoCrearTrabajo

logger = logging.getLogger(__name__)


def _manejar_crear_trabajo(valor, mensaje):
    """Traduce el comando de integración a un comando de aplicación."""
    from gestion_trabajos.seedwork.aplicacion.comandos import ejecutar_comando

    from ..aplicacion.comandos.crear_trabajo import CrearTrabajo

    datos = valor.data
    logger.info('Comando recibido: %s', datos)

    ejecutar_comando(CrearTrabajo(
        canal=datos.canal,
        partner_id=datos.partner_id,
        referencia_externa=datos.referencia_externa,
        categoria=datos.categoria,
        urgencia=datos.urgencia,
        pais=datos.pais,
        ciudad=datos.ciudad,
        direccion=datos.direccion,
        descripcion=datos.descripcion,
    ))


def suscribirse_a_comandos(app=None):
    import re

    # Por patrón, no por región: una réplica cubre las regiones existentes y las
    # que se agreguen en caliente (CA-8.4) sin reconfigurar nada.
    #
    # Shared: cada comando crea un trabajo distinto, así que no hay orden que
    # preservar y el consumo escala sin techo.
    correr(
        topicos=re.compile(patron_cmd_trabajo()),
        suscripcion=SUSCRIPCION_COMANDOS,
        schema=ComandoCrearTrabajo,
        manejar=_manejar_crear_trabajo,
        tipo=pulsar.ConsumerType.Shared,
        app=app,
    )
