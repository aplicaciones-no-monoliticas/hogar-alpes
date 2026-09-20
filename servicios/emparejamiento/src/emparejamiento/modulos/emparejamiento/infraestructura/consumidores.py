"""Los dos consumidores de Emparejamiento (§3.2 y §5.1 del plan técnico):

- `manejar_evento_trabajo` — suscripción REGIONAL a `evt-trabajo-{región}`
  (Failover, EMP-3). Solo `TrabajoCreado` dispara `EmparejarTrabajo`; un
  `EstadoTrabajoCambiado` se ignora (log y ack) porque el emparejamiento ya
  ocurrió con la creación.
- `manejar_evento_acreditacion` — suscripción `emparejamiento-proyeccion` a
  `evt-acreditacion` (Failover, EMP-2), la capa anticorrupción de la
  proyección.

Van en hilos separados (ver `consumidor.py`) porque son dos suscripciones
independientes con su propio ciclo de vida — no porque compartan lógica.
"""
import logging

from emparejamiento.config.topicos import (
    SUSCRIPCION_PROYECCION,
    SUSCRIPCION_SAGA,
    region,
    suscripcion_regional,
    topico_evt_acreditacion,
    topico_evt_trabajo,
)
from emparejamiento.seedwork.aplicacion.comandos import ejecutar_comando
from emparejamiento.seedwork.infraestructura import correlacion

from .schema.v1.evt_acreditacion import TIPO_VIGENCIA_RECHAZADA, AcreditacionActualizada
from .schema.v1.evt_trabajo import TIPO_CREADO, TIPO_ESTADO_CAMBIADO, EventoTrabajo

logger = logging.getLogger(__name__)


def manejar_evento_trabajo(valor, mensaje):
    from ..aplicacion.comandos.emparejar_trabajo import EmparejarTrabajo
    from ..aplicacion.comandos.liberar_reserva import LiberarReserva

    correlacion.agregar_campos(trabajo_id=valor.trabajo_id)

    if valor.type == TIPO_CREADO:
        simular_fallo = (mensaje.properties() or {}).get('simular_fallo', '')
        ejecutar_comando(EmparejarTrabajo(
            trabajo_id=valor.trabajo_id,
            region=region(),
            categoria=valor.categoria,
            pais=valor.pais,
            ciudad=valor.ciudad,
            simular_fallo=simular_fallo,
        ))
        logger.info('evt-trabajo procesado: trabajo_id=%s region=%s', valor.trabajo_id, region())
        return

    if valor.type == TIPO_ESTADO_CAMBIADO and valor.estado == 'CANCELADO':
        # Saga (US2, T041): falla en la asignación final (`ASIGNACION`) — GT ya
        # canceló el trabajo sin publicar `vigencia-rechazada`; si este servicio
        # todavía tiene una reserva activa para él, es la única señal de que
        # debe liberarla. No-op si ya se liberó (idempotente).
        ejecutar_comando(LiberarReserva(trabajo_id=valor.trabajo_id, motivo='ASIGNACION_FALLIDA'))
        logger.info('evt-trabajo (cancelado) procesado: trabajo_id=%s', valor.trabajo_id)
        return

    logger.info('evt-trabajo ignorado: %s', valor.type)


def manejar_evento_acreditacion(valor, mensaje):
    from ..aplicacion.comandos.actualizar_proveedor_candidato import (
        ActualizarProveedorCandidato,
    )

    ejecutar_comando(ActualizarProveedorCandidato(
        proveedor_id=valor.proveedor_id,
        pais=valor.pais,
        ciudad=valor.ciudad,
        categorias=list(valor.categorias),
        nivel=valor.nivel,
        estado=valor.estado,
        vigente_hasta=valor.vigente_hasta,
        version=valor.version,
    ))
    logger.info(
        'evt-acreditacion procesado: proveedor_id=%s estado=%s version=%s',
        valor.proveedor_id, valor.estado, valor.version,
    )


def manejar_evento_acreditacion_saga(valor, mensaje):
    """Suscripción `emparejamiento-saga` sobre `evt-acreditacion` (D6): solo le
    importa `vigencia-rechazada`, lo demás lo descarta por `type` sin tocar
    ninguna lógica de negocio (mismo patrón que `manejar_evento_acreditacion`)."""
    from ..aplicacion.comandos.liberar_reserva import LiberarReserva

    if valor.type != TIPO_VIGENCIA_RECHAZADA:
        logger.info('evt-acreditacion (saga) ignorado: %s', valor.type)
        return

    correlacion.agregar_campos(trabajo_id=valor.trabajo_id)
    ejecutar_comando(LiberarReserva(trabajo_id=valor.trabajo_id, motivo='VIGENCIA_RECHAZADA'))
    logger.info('vigencia-rechazada procesada: trabajo_id=%s proveedor_id=%s',
                valor.trabajo_id, valor.proveedor_id)


def suscribirse_regional(app):
    from emparejamiento.consumidor import correr

    correr(
        [topico_evt_trabajo()],
        suscripcion_regional(),
        EventoTrabajo,
        manejar_evento_trabajo,
        app=app,
    )


def suscribirse_proyeccion(app):
    from emparejamiento.consumidor import correr

    correr(
        [topico_evt_acreditacion()],
        SUSCRIPCION_PROYECCION,
        AcreditacionActualizada,
        manejar_evento_acreditacion,
        app=app,
    )


def suscribirse_saga(app):
    import pulsar

    from emparejamiento.consumidor import correr

    correr(
        [topico_evt_acreditacion()],
        SUSCRIPCION_SAGA,
        AcreditacionActualizada,
        manejar_evento_acreditacion_saga,
        tipo=pulsar.ConsumerType.Shared,
        app=app,
    )
