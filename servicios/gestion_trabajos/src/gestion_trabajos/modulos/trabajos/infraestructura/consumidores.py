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

from gestion_trabajos.config.topicos import (
    SUSCRIPCION_COMANDOS,
    SUSCRIPCION_SAGA,
    patron_cmd_trabajo,
    topico_evt_acreditacion,
    topico_evt_emparejamiento,
)
from gestion_trabajos.seedwork.infraestructura import correlacion
from gestion_trabajos.seedwork.infraestructura.consumidores import correr

from .schema.v1.comandos import ComandoCrearTrabajo
from .schema.v1.evt_acreditacion import (
    TIPO_VIGENCIA_CONFIRMADA,
    TIPO_VIGENCIA_RECHAZADA,
    AcreditacionActualizada,
)
from .schema.v1.evt_emparejamiento import TIPO_SIN_CANDIDATOS, EventoEmparejamiento

logger = logging.getLogger(__name__)


def _manejar_crear_trabajo(valor, mensaje):
    """Traduce el comando de integración (CON-1, contrato plano) a un comando
    de aplicación. `trabajo_id` viaja en el mensaje (GT-4): si el productor
    reintenta, `CrearTrabajoHandler` lo reconoce y no crea un segundo trabajo
    — la idempotencia vive en la aplicación, no aquí."""
    from gestion_trabajos.seedwork.aplicacion.comandos import ejecutar_comando

    from ..aplicacion.comandos.crear_trabajo import CrearTrabajo

    correlacion.agregar_campos(trabajo_id=valor.trabajo_id)
    logger.info('Comando recibido: trabajo_id=%s', valor.trabajo_id)

    simular_fallo = (mensaje.properties() or {}).get('simular_fallo', '')
    ejecutar_comando(CrearTrabajo(
        trabajo_id=valor.trabajo_id,
        canal=valor.canal,
        partner_id=valor.partner_id,
        referencia_externa=valor.referencia_externa,
        categoria=valor.categoria,
        urgencia=valor.urgencia,
        pais=valor.pais,
        ciudad=valor.ciudad,
        direccion=valor.direccion,
        descripcion=valor.descripcion,
        simular_fallo=simular_fallo,
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


def _manejar_evento_emparejamiento(valor, mensaje):
    """Suscripción `gestion-trabajos-saga` sobre `evt-emparejamiento` (D6):
    solo le importa `sin-candidatos`, lo demás lo descarta por `type` (R5-1)."""
    from gestion_trabajos.seedwork.aplicacion.comandos import ejecutar_comando

    from ..aplicacion.comandos.cancelar_sin_candidatos import CancelarSinCandidatos

    if valor.type != TIPO_SIN_CANDIDATOS:
        logger.info('evt-emparejamiento ignorado: %s', valor.type)
        return

    correlacion.agregar_campos(trabajo_id=valor.trabajo_id)
    ejecutar_comando(CancelarSinCandidatos(trabajo_id=valor.trabajo_id))
    logger.info('sin-candidatos procesado: trabajo_id=%s', valor.trabajo_id)


def _manejar_evento_acreditacion(valor, mensaje):
    """Suscripción `gestion-trabajos-saga` sobre `evt-acreditacion` (D6, R5-1):
    también recibe el tráfico masivo de `actualizada` del escenario de
    escalabilidad — se descarta por `type` antes de cualquier lógica de
    negocio, sin decodificar el resto del mensaje."""
    from gestion_trabajos.seedwork.aplicacion.comandos import ejecutar_comando

    from ..aplicacion.comandos.cancelar_vigencia_rechazada import CancelarVigenciaRechazada
    from ..aplicacion.comandos.confirmar_asignacion import ConfirmarAsignacion

    if valor.type not in (TIPO_VIGENCIA_CONFIRMADA, TIPO_VIGENCIA_RECHAZADA):
        return

    correlacion.agregar_campos(trabajo_id=valor.trabajo_id)
    if valor.type == TIPO_VIGENCIA_CONFIRMADA:
        simular_fallo = (mensaje.properties() or {}).get('simular_fallo', '')
        ejecutar_comando(ConfirmarAsignacion(
            trabajo_id=valor.trabajo_id, proveedor_id=valor.proveedor_id,
            simular_fallo=simular_fallo,
        ))
    else:
        ejecutar_comando(CancelarVigenciaRechazada(trabajo_id=valor.trabajo_id))
    logger.info('%s procesado: trabajo_id=%s', valor.type, valor.trabajo_id)


def suscribirse_saga_emparejamiento(app=None):
    correr(
        topicos=[topico_evt_emparejamiento()],
        suscripcion=SUSCRIPCION_SAGA,
        schema=EventoEmparejamiento,
        manejar=_manejar_evento_emparejamiento,
        tipo=pulsar.ConsumerType.Shared,
        app=app,
    )


def suscribirse_saga_acreditacion(app=None):
    correr(
        topicos=[topico_evt_acreditacion()],
        suscripcion=SUSCRIPCION_SAGA,
        schema=AcreditacionActualizada,
        manejar=_manejar_evento_acreditacion,
        tipo=pulsar.ConsumerType.Shared,
        app=app,
    )
