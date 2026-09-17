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
    region,
    suscripcion_regional,
    topico_evt_acreditacion,
    topico_evt_trabajo,
)
from emparejamiento.seedwork.aplicacion.comandos import ejecutar_comando

from .schema.v1.evt_acreditacion import AcreditacionActualizada
from .schema.v1.evt_trabajo import TIPO_CREADO, EventoTrabajo

logger = logging.getLogger(__name__)


def manejar_evento_trabajo(valor, mensaje):
    from ..aplicacion.comandos.emparejar_trabajo import EmparejarTrabajo

    if valor.type != TIPO_CREADO:
        logger.info('evt-trabajo ignorado (no es creación): %s', valor.type)
        return

    ejecutar_comando(EmparejarTrabajo(
        trabajo_id=valor.trabajo_id,
        region=region(),
        categoria=valor.categoria,
        pais=valor.pais,
        ciudad=valor.ciudad,
    ))
    logger.info('evt-trabajo procesado: trabajo_id=%s region=%s', valor.trabajo_id, region())


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
