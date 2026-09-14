"""OPS-2 · OPS-3 — AbrirSeguimiento y RegistrarCambioEstado: aplicación,
deduplicación por `evento_id` y el caso HUERFANO (CA-6.5)."""
import pytest

from operaciones import crear_app
from operaciones.modulos.operaciones.aplicacion.comandos.abrir_seguimiento import (
    AbrirSeguimiento,
)
from operaciones.modulos.operaciones.aplicacion.comandos.registrar_cambio_estado import (
    RegistrarCambioEstado,
)
from operaciones.modulos.operaciones.aplicacion.queries.obtener_seguimiento import (
    ObtenerSeguimientoDeTrabajo,
)
from operaciones.seedwork.aplicacion.comandos import ejecutar_comando
from operaciones.seedwork.aplicacion.queries import ejecutar_query


@pytest.fixture
def app():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app


def _abrir(evento_id='e1', trabajo_id='t1', urgencia='NORMAL'):
    return ejecutar_comando(AbrirSeguimiento(
        evento_id=evento_id, trabajo_id=trabajo_id, pais='CO', canal='app',
        categoria='PLOMERIA', estado='CREADO', urgencia=urgencia,
    ))


def test_abrir_seguimiento_aplica_la_primera_vez(app):
    resultado = _abrir()
    assert resultado == 'APLICADO'
    seguimiento = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id='t1')).resultado
    assert seguimiento['estado_trabajo'] == 'CREADO'


def test_abrir_seguimiento_reentregado_es_duplicado_por_evento_id(app):
    _abrir()
    resultado = _abrir()  # mismo evento_id, misma reentrega
    assert resultado == 'DUPLICADO'


def test_abrir_seguimiento_para_el_mismo_trabajo_es_duplicado_por_trabajo_id(app):
    _abrir(evento_id='e1', trabajo_id='t1')
    resultado = _abrir(evento_id='e2', trabajo_id='t1')  # evento distinto, mismo trabajo
    assert resultado == 'DUPLICADO'


def test_registrar_cambio_estado_aplica_si_hay_seguimiento(app):
    _abrir(trabajo_id='t2')
    resultado = ejecutar_comando(RegistrarCambioEstado(
        evento_id='e-estado-1', trabajo_id='t2',
        estado_nuevo='ASIGNADO', estado_anterior='CREADO',
    ))
    assert resultado == 'APLICADO'
    seguimiento = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id='t2')).resultado
    assert seguimiento['estado_trabajo'] == 'ASIGNADO'


def test_registrar_cambio_estado_sin_seguimiento_es_huerfano_no_se_descarta(app):
    """CA-6.5: el cambio de estado llega antes que la creación (o tras una
    ventana perdida) y NO se pierde en silencio — queda registrado."""
    resultado = ejecutar_comando(RegistrarCambioEstado(
        evento_id='e-huerfano-1', trabajo_id='no-existe',
        estado_nuevo='ASIGNADO', estado_anterior='CREADO',
    ))
    assert resultado == 'HUERFANO'


def test_registrar_cambio_estado_reentregado_es_duplicado(app):
    _abrir(trabajo_id='t3')
    ejecutar_comando(RegistrarCambioEstado(
        evento_id='e-estado-2', trabajo_id='t3',
        estado_nuevo='ASIGNADO', estado_anterior='CREADO',
    ))
    resultado = ejecutar_comando(RegistrarCambioEstado(
        evento_id='e-estado-2', trabajo_id='t3',
        estado_nuevo='ASIGNADO', estado_anterior='CREADO',
    ))
    assert resultado == 'DUPLICADO'


def test_orden_por_trabajo_id_creado_antes_que_estado(app):
    """Dentro de un mismo trabajo_id, aplicar los eventos en el orden en que
    los publicaría GT (creación, luego estados) dejan la secuencia esperada."""
    _abrir(evento_id='e1', trabajo_id='t4')
    ejecutar_comando(RegistrarCambioEstado(
        evento_id='e2', trabajo_id='t4', estado_nuevo='ASIGNADO', estado_anterior='CREADO',
    ))
    ejecutar_comando(RegistrarCambioEstado(
        evento_id='e3', trabajo_id='t4', estado_nuevo='EN_EJECUCION', estado_anterior='ASIGNADO',
    ))
    seguimiento = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id='t4')).resultado
    assert seguimiento['estado_trabajo'] == 'EN_EJECUCION'
