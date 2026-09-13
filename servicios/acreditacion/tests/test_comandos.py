"""ACR-5 · comando repetido — los tres comandos son idempotentes ante
reentrega, que es la garantía real que pide `cmd-acreditacion` (Failover, pero
con `negative_acknowledge` reintentando)."""
import uuid

import pytest

from acreditacion import crear_app
from acreditacion.modulos.acreditacion.aplicacion.comandos.aprobar_acreditacion import (
    AprobarAcreditacion,
)
from acreditacion.modulos.acreditacion.aplicacion.comandos.revocar_acreditacion import (
    RevocarAcreditacion,
)
from acreditacion.modulos.acreditacion.aplicacion.comandos.solicitar_acreditacion import (
    SolicitarAcreditacion,
)
from acreditacion.modulos.acreditacion.dominio.excepciones import AcreditacionNoExisteExcepcion
from acreditacion.seedwork.aplicacion.comandos import ejecutar_comando


@pytest.fixture
def app():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app


def _solicitar(app, acreditacion_id=None):
    return ejecutar_comando(SolicitarAcreditacion(
        proveedor_id='prov-1', pais='CO', ciudad='Bogota',
        categorias=['PLOMERIA'], nivel='ORO', vigencia_meses=12,
        acreditacion_id=acreditacion_id or '',
    ))


def test_solicitar_repetido_con_el_mismo_id_no_duplica(app):
    acreditacion_id = str(uuid.uuid4())

    primero = _solicitar(app, acreditacion_id)
    segundo = _solicitar(app, acreditacion_id)

    assert primero == segundo == acreditacion_id


def test_aprobar_repetido_no_falla(app):
    id_ = _solicitar(app)

    ejecutar_comando(AprobarAcreditacion(acreditacion_id=id_))
    # Reentrega del mismo comando: no debe romper la regla de transición.
    ejecutar_comando(AprobarAcreditacion(acreditacion_id=id_))


def test_aprobar_sobre_id_inexistente_falla(app):
    with pytest.raises(AcreditacionNoExisteExcepcion):
        ejecutar_comando(AprobarAcreditacion(acreditacion_id=str(uuid.uuid4())))


def test_revocar_repetido_no_falla(app):
    id_ = _solicitar(app)
    ejecutar_comando(AprobarAcreditacion(acreditacion_id=id_))

    ejecutar_comando(RevocarAcreditacion(acreditacion_id=id_))
    ejecutar_comando(RevocarAcreditacion(acreditacion_id=id_))
