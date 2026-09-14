"""OPS-2 — la capa anticorrupción (`manejar_evento_trabajo`), probada sin
broker: se le pasa un objeto con la misma forma que `EventoTrabajo` (los campos
que el handler lee), no un mensaje real de Pulsar. La conexión real al clúster
la verifica `escenarios/escenario-6.sh`.
"""
from dataclasses import dataclass

import pytest

from operaciones import crear_app
from operaciones.modulos.operaciones.aplicacion.queries.obtener_seguimiento import (
    ObtenerSeguimientoDeTrabajo,
)
from operaciones.modulos.operaciones.infraestructura.consumidores import (
    manejar_evento_trabajo,
)
from operaciones.modulos.operaciones.infraestructura.schema.v1.evt_trabajo import (
    TIPO_CREADO,
    TIPO_ESTADO_CAMBIADO,
)
from operaciones.seedwork.aplicacion.queries import ejecutar_query


@dataclass
class _EventoFalso:
    id: str
    type: str
    trabajo_id: str
    pais: str = 'CO'
    canal: str = 'app'
    categoria: str = 'PLOMERIA'
    estado: str = 'CREADO'
    urgencia: str = 'NORMAL'
    estado_anterior: str = ''


@pytest.fixture
def app():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app


def test_creado_abre_el_seguimiento(app):
    manejar_evento_trabajo(
        _EventoFalso(id='e1', type=TIPO_CREADO, trabajo_id='t1'), mensaje=None,
    )
    seguimiento = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id='t1')).resultado
    assert seguimiento is not None


def test_estado_cambiado_sobre_seguimiento_existente_lo_actualiza(app):
    manejar_evento_trabajo(
        _EventoFalso(id='e1', type=TIPO_CREADO, trabajo_id='t2'), mensaje=None,
    )
    manejar_evento_trabajo(
        _EventoFalso(
            id='e2', type=TIPO_ESTADO_CAMBIADO, trabajo_id='t2',
            estado='ASIGNADO', estado_anterior='CREADO',
        ),
        mensaje=None,
    )
    seguimiento = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id='t2')).resultado
    assert seguimiento['estado_trabajo'] == 'ASIGNADO'


def test_estado_cambiado_sin_creado_no_revienta_y_queda_huerfano(app):
    """No debe lanzar: el mensaje se confirma (`ack`) igual, porque quedó
    contabilizado como HUERFANO, no perdido (CA-6.5)."""
    manejar_evento_trabajo(
        _EventoFalso(
            id='e-huerfano', type=TIPO_ESTADO_CAMBIADO, trabajo_id='no-existe',
            estado='ASIGNADO', estado_anterior='CREADO',
        ),
        mensaje=None,
    )
    seguimiento = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id='no-existe')).resultado
    assert seguimiento is None


def test_type_desconocido_se_ignora_sin_error(app):
    manejar_evento_trabajo(
        _EventoFalso(id='e-x', type='hogaralpes.trabajo.algo-mas.v1', trabajo_id='t3'),
        mensaje=None,
    )
    seguimiento = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id='t3')).resultado
    assert seguimiento is None
