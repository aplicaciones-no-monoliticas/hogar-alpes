"""OPS-3 — el borde HTTP, con el cliente de pruebas de Flask."""
import pytest

from operaciones import crear_app
from operaciones.modulos.operaciones.aplicacion.comandos.abrir_seguimiento import (
    AbrirSeguimiento,
)
from operaciones.seedwork.aplicacion.comandos import ejecutar_comando


@pytest.fixture
def client():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app.test_client()


def test_get_seguimiento(client):
    ejecutar_comando(AbrirSeguimiento(
        evento_id='e1', trabajo_id='t1', pais='CO', canal='app',
        categoria='PLOMERIA', estado='CREADO', urgencia='ALTA',
    ))

    resp = client.get('/seguimientos/t1')
    assert resp.status_code == 200
    assert resp.json['trabajo_id'] == 't1'
    assert resp.json['prioridad'] == 'P2'


def test_get_seguimiento_inexistente_404(client):
    resp = client.get('/seguimientos/no-existe')
    assert resp.status_code == 404


def test_get_conteo(client):
    ejecutar_comando(AbrirSeguimiento(
        evento_id='e1', trabajo_id='t1', pais='CO', canal='app',
        categoria='PLOMERIA', estado='CREADO', urgencia='NORMAL',
    ))
    ejecutar_comando(AbrirSeguimiento(
        evento_id='e2', trabajo_id='t2', pais='CO', canal='app',
        categoria='PLOMERIA', estado='CREADO', urgencia='NORMAL',
    ))

    resp = client.get('/seguimientos/conteo')
    assert resp.status_code == 200
    assert resp.json['total'] == 2


def test_health(client):
    resp = client.get('/health')
    assert resp.status_code == 200


def test_get_conteo_eventos_procesados(client):
    ejecutar_comando(AbrirSeguimiento(
        evento_id='e1', trabajo_id='t1', pais='CO', canal='app',
        categoria='PLOMERIA', estado='CREADO', urgencia='NORMAL',
    ))
    # Un TrabajoCreado distinto (evento_id distinto) para el MISMO trabajo_id:
    # se registra como DUPLICADO — a diferencia de la reentrega EXACTA del
    # mismo evento_id, que no llega a insertar una segunda fila (su PK ya
    # existe) y por eso no aparece en este conteo.
    ejecutar_comando(AbrirSeguimiento(
        evento_id='e2', trabajo_id='t1', pais='CO', canal='app',
        categoria='PLOMERIA', estado='CREADO', urgencia='NORMAL',
    ))

    aplicados = client.get('/eventos-procesados/conteo?resultado=APLICADO')
    duplicados = client.get('/eventos-procesados/conteo?resultado=DUPLICADO')
    assert aplicados.json['total'] == 1
    assert duplicados.json['total'] == 1
