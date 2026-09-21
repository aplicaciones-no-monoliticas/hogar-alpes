"""Los tres consumidores de `saga_log` (D6/D9/D11 de research.md): observan
`evt-trabajo-.*`, `evt-emparejamiento` y `evt-acreditacion`, y descartan
silenciosamente cualquier `type` que no reconozcan para su propósito — nunca
publican nada (CA-1.16).
"""
import logging

from saga_log.config.topicos import (
    SUSCRIPCION,
    patron_evt_trabajo,
    topico_evt_acreditacion,
    topico_evt_emparejamiento,
)
from saga_log.seedwork.infraestructura import correlacion

from .repositorios import RepositorioSagas
from .schema.v1.evt_acreditacion import (
    TIPO_VIGENCIA_CONFIRMADA,
    TIPO_VIGENCIA_RECHAZADA,
    AcreditacionActualizada,
)
from .schema.v1.evt_emparejamiento import (
    TIPO_CANDIDATOS,
    TIPO_CANDIDATOS_LIBERADOS,
    TIPO_PROVEEDOR_PROPUESTO,
    TIPO_SIN_CANDIDATOS,
    EventoEmparejamiento,
)
from .schema.v1.evt_trabajo import TIPO_CREADO, TIPO_ESTADO_CAMBIADO, EventoTrabajo

logger = logging.getLogger(__name__)

_TIPOS_TRABAJO = {TIPO_CREADO, TIPO_ESTADO_CAMBIADO}
_TIPOS_EMPAREJAMIENTO = {
    TIPO_CANDIDATOS, TIPO_SIN_CANDIDATOS, TIPO_PROVEEDOR_PROPUESTO, TIPO_CANDIDATOS_LIBERADOS,
}
_TIPOS_ACREDITACION = {TIPO_VIGENCIA_CONFIRMADA, TIPO_VIGENCIA_RECHAZADA}


def _ocurrido_en(valor):
    from datetime import datetime
    # `time` es milisegundos desde época (mismo formato que `unix_time_millis`
    # usa el resto del sistema para construir el sobre).
    return datetime.utcfromtimestamp((valor.time or 0) / 1000.0)


def manejar_evento_trabajo(valor, mensaje):
    if valor.type not in _TIPOS_TRABAJO:
        logger.info('evt-trabajo ignorado: %s', valor.type)
        return

    correlacion.agregar_campos(trabajo_id=valor.trabajo_id)
    RepositorioSagas().registrar_paso(
        mensaje_id=valor.id, trabajo_id=valor.trabajo_id, correlation_id=valor.correlation_id,
        servicio='gestion-trabajos', tipo=valor.type, ocurrido_en=_ocurrido_en(valor),
        estado_mensaje=valor.estado,
    )
    logger.info('paso registrado: %s trabajo_id=%s', valor.type, valor.trabajo_id)


def manejar_evento_emparejamiento(valor, mensaje):
    if valor.type not in _TIPOS_EMPAREJAMIENTO:
        logger.info('evt-emparejamiento ignorado: %s', valor.type)
        return

    correlacion.agregar_campos(trabajo_id=valor.trabajo_id)
    RepositorioSagas().registrar_paso(
        mensaje_id=valor.id, trabajo_id=valor.trabajo_id, correlation_id=valor.correlation_id,
        servicio='emparejamiento', tipo=valor.type, ocurrido_en=_ocurrido_en(valor),
    )
    logger.info('paso registrado: %s trabajo_id=%s', valor.type, valor.trabajo_id)


def manejar_evento_acreditacion(valor, mensaje):
    """`AcreditacionActualizada` (snapshot, sin `trabajo_id`) se descarta aquí
    por `type` desconocido para la saga — es el edge case de D8: un mensaje que
    no se puede asociar a ninguna transacción conocida."""
    if valor.type not in _TIPOS_ACREDITACION:
        logger.info('evt-acreditacion ignorado: %s', valor.type)
        return

    correlacion.agregar_campos(trabajo_id=valor.trabajo_id)
    RepositorioSagas().registrar_paso(
        mensaje_id=valor.id, trabajo_id=valor.trabajo_id, correlation_id=valor.correlation_id,
        servicio='acreditacion', tipo=valor.type, ocurrido_en=_ocurrido_en(valor),
    )
    logger.info('paso registrado: %s trabajo_id=%s', valor.type, valor.trabajo_id)


def suscribirse_trabajo(app):
    import re

    import pulsar

    from saga_log.consumidor import correr

    correr(
        re.compile(patron_evt_trabajo()), SUSCRIPCION, EventoTrabajo,
        manejar_evento_trabajo, tipo=pulsar.ConsumerType.Shared, app=app,
    )


def suscribirse_emparejamiento(app):
    import pulsar

    from saga_log.consumidor import correr

    correr(
        [topico_evt_emparejamiento()], SUSCRIPCION, EventoEmparejamiento,
        manejar_evento_emparejamiento, tipo=pulsar.ConsumerType.Shared, app=app,
    )


def suscribirse_acreditacion(app):
    import pulsar

    from saga_log.consumidor import correr

    correr(
        [topico_evt_acreditacion()], SUSCRIPCION, AcreditacionActualizada,
        manejar_evento_acreditacion, tipo=pulsar.ConsumerType.Shared, app=app,
    )
