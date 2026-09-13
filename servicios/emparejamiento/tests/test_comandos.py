"""EMP-3 · EMP-5 — EmparejarTrabajo: candidatos identificados, sin candidatos,
idempotencia ante reentrega del mismo `trabajo_id`."""
from datetime import date, timedelta

import pytest

from emparejamiento import crear_app
from emparejamiento.modulos.emparejamiento.aplicacion.comandos.actualizar_proveedor_candidato import (
    ActualizarProveedorCandidato,
)
from emparejamiento.modulos.emparejamiento.aplicacion.comandos.emparejar_trabajo import (
    EmparejarTrabajo,
)
from emparejamiento.modulos.emparejamiento.aplicacion.queries.obtener_emparejamiento import (
    ObtenerEmparejamiento,
)
from emparejamiento.seedwork.aplicacion.comandos import ejecutar_comando
from emparejamiento.seedwork.aplicacion.queries import ejecutar_query

MANANA = (date.today() + timedelta(days=1)).isoformat()


@pytest.fixture
def app():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app


def _acreditar(proveedor_id='p1', categoria='PLOMERIA'):
    ejecutar_comando(ActualizarProveedorCandidato(
        proveedor_id=proveedor_id, pais='CO', ciudad='Bogota',
        categorias=[categoria], nivel='ORO', estado='ACREDITADA',
        vigente_hasta=MANANA, version=1,
    ))


def test_emparejar_con_candidatos_acreditados(app):
    _acreditar()

    trabajo_id = ejecutar_comando(EmparejarTrabajo(
        trabajo_id='11111111-1111-1111-1111-111111111111', region='andina',
        categoria='PLOMERIA', pais='CO', ciudad='Bogota',
    ))

    resultado = ejecutar_query(ObtenerEmparejamiento(trabajo_id=trabajo_id)).resultado
    assert resultado['candidatos'] == ['p1']
    assert resultado['total'] == 1
    assert resultado['region'] == 'andina'


def test_emparejar_sin_candidatos_acreditados(app):
    trabajo_id = ejecutar_comando(EmparejarTrabajo(
        trabajo_id='22222222-2222-2222-2222-222222222222', region='andina',
        categoria='PLOMERIA', pais='CO', ciudad='Bogota',
    ))

    resultado = ejecutar_query(ObtenerEmparejamiento(trabajo_id=trabajo_id)).resultado
    assert resultado['candidatos'] == []
    assert resultado['total'] == 0


def test_emparejar_repetido_para_el_mismo_trabajo_es_idempotente(app):
    _acreditar()
    trabajo_id = '33333333-3333-3333-3333-333333333333'

    primero = ejecutar_comando(EmparejarTrabajo(
        trabajo_id=trabajo_id, region='andina', categoria='PLOMERIA', pais='CO', ciudad='Bogota',
    ))
    # Un segundo proveedor se acredita DESPUÉS del primer emparejamiento: si el
    # comando no fuera idempotente, la reentrega lo recogería y el resultado
    # cambiaría, lo que rompe la garantía de "un emparejamiento por trabajo".
    _acreditar(proveedor_id='p2')
    segundo = ejecutar_comando(EmparejarTrabajo(
        trabajo_id=trabajo_id, region='andina', categoria='PLOMERIA', pais='CO', ciudad='Bogota',
    ))

    assert primero == segundo
    resultado = ejecutar_query(ObtenerEmparejamiento(trabajo_id=trabajo_id)).resultado
    assert resultado['candidatos'] == ['p1']
