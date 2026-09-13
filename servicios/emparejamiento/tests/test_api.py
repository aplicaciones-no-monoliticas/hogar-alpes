"""EMP-4 · consultas — el borde HTTP, con el cliente de pruebas de Flask."""
from datetime import date, timedelta

import pytest

from emparejamiento import crear_app
from emparejamiento.modulos.emparejamiento.aplicacion.comandos.actualizar_proveedor_candidato import (
    ActualizarProveedorCandidato,
)
from emparejamiento.modulos.emparejamiento.aplicacion.comandos.emparejar_trabajo import (
    EmparejarTrabajo,
)
from emparejamiento.seedwork.aplicacion.comandos import ejecutar_comando

MANANA = (date.today() + timedelta(days=1)).isoformat()


@pytest.fixture
def client():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app.test_client()


def test_get_candidatos(client):
    ejecutar_comando(ActualizarProveedorCandidato(
        proveedor_id='p1', pais='CO', ciudad='Bogota', categorias=['PLOMERIA'],
        nivel='ORO', estado='ACREDITADA', vigente_hasta=MANANA, version=1,
    ))

    resp = client.get('/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota')
    assert resp.status_code == 200
    assert [c['proveedor_id'] for c in resp.json] == ['p1']


def test_get_emparejamiento(client):
    trabajo_id = ejecutar_comando(EmparejarTrabajo(
        trabajo_id='44444444-4444-4444-4444-444444444444', region='andina',
        categoria='PLOMERIA', pais='CO', ciudad='Bogota',
    ))

    resp = client.get(f'/emparejamientos/{trabajo_id}')
    assert resp.status_code == 200
    assert resp.json['trabajo_id'] == trabajo_id


def test_get_emparejamiento_inexistente_404(client):
    resp = client.get('/emparejamientos/no-existe')
    assert resp.status_code == 404


def test_health(client):
    resp = client.get('/health')
    assert resp.status_code == 200
