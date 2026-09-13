"""ACR-4 · consultas — el borde HTTP completo, con el cliente de pruebas de
Flask. No hace falta un servidor real ni PostgreSQL: `crear_app()` sin
`DATABASE_URI` usa SQLite en memoria (igual que el resto de la suite)."""
import pytest

from acreditacion import crear_app


@pytest.fixture
def client():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app.test_client()


def test_flujo_completo_solicitar_aprobar_consultar(client):
    resp = client.post('/acreditaciones', json={
        'proveedor_id': 'prov-9', 'pais': 'CO', 'ciudad': 'Bogota',
        'categorias': ['PLOMERIA', 'GAS'], 'nivel': 'ORO', 'vigencia_meses': 12,
    })
    assert resp.status_code == 202
    id_ = resp.json['id']

    resp = client.get(f'/acreditaciones/{id_}')
    assert resp.status_code == 200
    assert resp.json['estado'] == 'SOLICITADA'
    assert resp.json['version'] == 1

    resp = client.put(f'/acreditaciones/{id_}/aprobar', json={'motivo': 'ok'})
    assert resp.status_code == 202

    resp = client.get(f'/acreditaciones/{id_}')
    assert resp.json['estado'] == 'ACREDITADA'
    assert resp.json['vigente_hasta']
    assert resp.json['version'] == 2

    resp = client.get(f'/acreditaciones/{id_}/eventos')
    assert resp.status_code == 200
    assert [e['tipo'] for e in resp.json] == ['AcreditacionSolicitada', 'AcreditacionAprobada']

    resp = client.put(f'/acreditaciones/{id_}/revocar', json={'motivo': 'denuncia'})
    assert resp.status_code == 202
    assert client.get(f'/acreditaciones/{id_}').json['estado'] == 'REVOCADA'


def test_solicitar_sin_categorias_devuelve_400(client):
    resp = client.post('/acreditaciones', json={
        'proveedor_id': 'prov-9', 'pais': 'CO', 'ciudad': 'Bogota',
        'categorias': [], 'nivel': 'ORO', 'vigencia_meses': 12,
    })
    assert resp.status_code == 400


def test_aprobar_id_inexistente_devuelve_404(client):
    resp = client.put('/acreditaciones/no-existe/aprobar', json={})
    assert resp.status_code == 404


def test_obtener_id_inexistente_devuelve_404(client):
    resp = client.get('/acreditaciones/no-existe')
    assert resp.status_code == 404


def test_health(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.json['status'] == 'up'
