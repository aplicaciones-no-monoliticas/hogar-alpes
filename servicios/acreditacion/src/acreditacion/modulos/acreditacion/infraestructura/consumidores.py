"""Consumidor de `cmd-acreditacion`.

Un solo stream para los tres comandos, discriminados por `tipo_comando`
(ver `schema/v1/comandos.py`). La suscripción es Failover: el orden dentro de
un mismo `proveedor_id` importa —una aprobación no puede adelantar a su
solicitud—, así que solo hay un consumidor activo por partición.
"""
import logging

from acreditacion.config.topicos import SUSCRIPCION_COMANDOS, topico_cmd_acreditacion
from acreditacion.seedwork.aplicacion.comandos import ejecutar_comando

from .schema.v1.comandos import APROBAR, REVOCAR, SOLICITAR, ComandoAcreditacion

logger = logging.getLogger(__name__)


def manejar_comando(valor, mensaje):
    from ..aplicacion.comandos.aprobar_acreditacion import AprobarAcreditacion
    from ..aplicacion.comandos.revocar_acreditacion import RevocarAcreditacion
    from ..aplicacion.comandos.solicitar_acreditacion import SolicitarAcreditacion

    if valor.tipo_comando == SOLICITAR:
        acreditacion_id = ejecutar_comando(SolicitarAcreditacion(
            proveedor_id=valor.proveedor_id, pais=valor.pais, ciudad=valor.ciudad,
            categorias=list(valor.categorias), nivel=valor.nivel,
            vigencia_meses=valor.vigencia_meses, motivo=valor.motivo,
            acreditacion_id=valor.acreditacion_id,
        ))
        logger.info(
            'SOLICITAR proveedor_id=%s -> acreditacion_id=%s',
            valor.proveedor_id, acreditacion_id,
        )
    elif valor.tipo_comando == APROBAR:
        ejecutar_comando(AprobarAcreditacion(
            acreditacion_id=valor.acreditacion_id, motivo=valor.motivo,
        ))
        logger.info('APROBAR acreditacion_id=%s', valor.acreditacion_id)
    elif valor.tipo_comando == REVOCAR:
        ejecutar_comando(RevocarAcreditacion(
            acreditacion_id=valor.acreditacion_id, motivo=valor.motivo,
        ))
        logger.info('REVOCAR acreditacion_id=%s', valor.acreditacion_id)
    else:
        logger.warning('tipo_comando desconocido: %s', valor.tipo_comando)


def suscribirse(app):
    from acreditacion.consumidor import correr

    correr(
        [topico_cmd_acreditacion()],
        SUSCRIPCION_COMANDOS,
        ComandoAcreditacion,
        manejar_comando,
        app=app,
    )
