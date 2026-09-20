"""Reenvío fiel (CA-2.5, CA-2.7, FR-003, FR-005): misma ruta, cuerpo y código."""
import pytest

CUERPO = b'{"categoria": "PLOMERIA", "pais": "CO"}'

# (método, ruta concreta, servicio que debe recibirla) — las 17 rutas, escritas a mano.
LAS_17 = [
    ('POST', '/trabajos', 'gestion-trabajos'),
    ('GET', '/trabajos/abc', 'gestion-trabajos'),
    ('GET', '/trabajos', 'gestion-trabajos'),
    ('PUT', '/trabajos/abc/estado', 'gestion-trabajos'),
    ('GET', '/seguimientos/abc', 'operaciones'),
    ('GET', '/seguimientos/conteo', 'operaciones'),
    ('GET', '/eventos-procesados/conteo', 'operaciones'),
    ('POST', '/acreditaciones', 'acreditacion'),
    ('PUT', '/acreditaciones/abc/aprobar', 'acreditacion'),
    ('PUT', '/acreditaciones/abc/revocar', 'acreditacion'),
    ('GET', '/acreditaciones/abc', 'acreditacion'),
    ('GET', '/acreditaciones/abc/eventos', 'acreditacion'),
    ('GET', '/candidatos', 'emparejamiento'),
    ('GET', '/emparejamientos/abc', 'emparejamiento'),
    ('GET', '/sagas/abc', 'saga-log'),
    ('GET', '/sagas', 'saga-log'),
    ('GET', '/sagas/resumen', 'saga-log'),
]


def _llamar(cliente, metodo, ruta, con_cuerpo=False):
    if con_cuerpo:
        return cliente.open(ruta, method=metodo, data=CUERPO, content_type='application/json')
    return cliente.open(ruta, method=metodo, headers={'Accept': 'application/json'})


def test_hay_diecisiete_rutas_en_la_lista_literal():
    assert len(LAS_17) == 17
    assert len(set(LAS_17)) == 17


@pytest.mark.parametrize('metodo, ruta, servicio', LAS_17)
def test_cada_ruta_llega_al_servicio_correcto_sin_cambios(cliente, atras, metodo, ruta, servicio):
    atras[servicio].responder(metodo, ruta, 200, {'ok': True})
    con_cuerpo = metodo in ('POST', 'PUT')

    respuesta = _llamar(cliente, metodo, ruta, con_cuerpo)

    assert respuesta.status_code == 200
    assert respuesta.get_json()['ok'] is True
    recibida = atras[servicio].recibidas[-1]
    assert recibida['metodo'] == metodo
    assert recibida['ruta'] == ruta
    assert recibida['consulta'] == ''
    if con_cuerpo:
        assert recibida['cuerpo'] == CUERPO
        assert recibida['cabeceras']['content-type'] == 'application/json'
    else:
        assert recibida['cuerpo'] == b''
        assert recibida['cabeceras']['accept'] == 'application/json'
    otros = [s for nombre, s in atras.items() if nombre != servicio]
    assert [len(s.recibidas) for s in otros] == [0, 0, 0, 0]


def test_la_consulta_del_listado_de_trabajos_llega_identica(cliente, atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos', 200, [])

    cliente.get('/trabajos?estado=CREADO')

    recibida = atras['gestion-trabajos'].recibidas[-1]
    assert recibida['ruta'] == '/trabajos'
    assert recibida['consulta'] == 'estado=CREADO'


def test_la_consulta_de_candidatos_llega_identica(cliente, atras):
    atras['emparejamiento'].responder('GET', '/candidatos', 200, [])

    cliente.get('/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota')

    assert atras['emparejamiento'].recibidas[-1]['consulta'] == 'categoria=PLOMERIA&pais=CO&ciudad=Bogota'


@pytest.mark.parametrize('pedida, esperada', [
    ('/trabajos/a%3Fb', '/trabajos/a%3Fb'),
    ('/trabajos/a%23b', '/trabajos/a%23b'),
    ('/trabajos/a%20b', '/trabajos/a%20b'),
    ('/trabajos/a%0D%0Ab', '/trabajos/a%0D%0Ab'),
])
def test_un_id_con_caracteres_codificados_no_altera_la_ruta_ni_la_consulta(cliente, atras, pedida, esperada):
    atras['gestion-trabajos'].responder('GET', esperada, 200, {'ok': True})

    respuesta = cliente.get(pedida)

    assert respuesta.status_code == 200
    recibida = atras['gestion-trabajos'].recibidas[-1]
    assert recibida['ruta'] == esperada
    assert recibida['consulta'] == ''


def test_un_202_sigue_siendo_202_con_sus_campos(cliente, atras):
    atras['gestion-trabajos'].responder('POST', '/trabajos', 202, {'id': 'abc', 'estado': 'CREADO'})

    respuesta = cliente.post('/trabajos', data=CUERPO, content_type='application/json')

    assert respuesta.status_code == 202
    cuerpo = respuesta.get_json()
    assert cuerpo['id'] == 'abc'
    assert cuerpo['estado'] == 'CREADO'


@pytest.mark.parametrize('codigo, cuerpo', [
    (400, b'{"error": "categoria no permitida en MX"}'),
    (404, b'{"error": "Trabajo no encontrado"}'),
    (409, b'{"error": "transicion no permitida"}'),
])
def test_los_errores_de_negocio_llegan_con_el_mismo_codigo_y_los_mismos_bytes(cliente, atras, codigo, cuerpo):
    atras['gestion-trabajos'].responder('PUT', '/trabajos/abc/estado', codigo, cuerpo)

    respuesta = cliente.put('/trabajos/abc/estado', data=b'{"estado": "X"}', content_type='application/json')

    assert respuesta.status_code == codigo
    assert respuesta.data == cuerpo
    assert respuesta.content_type == 'application/json'
    assert b'grupos_disponibles' not in respuesta.data


def test_una_redireccion_del_servicio_no_se_sigue(cliente, atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos/abc', 308, b'', cabeceras={'Location': '/otra'})
    atras['gestion-trabajos'].responder('GET', '/otra', 200, {'ok': True})

    respuesta = cliente.get('/trabajos/abc')

    assert respuesta.status_code == 308
    assert respuesta.headers['Location'] == '/otra'
    assert [r['ruta'] for r in atras['gestion-trabajos'].recibidas] == ['/trabajos/abc']


@pytest.mark.parametrize('metodo, ruta, servicio', [
    ('GET', '/seguimientos/conteo', 'operaciones'),
    ('GET', '/sagas/resumen', 'saga-log'),
])
def test_las_rutas_estaticas_ganan_a_la_de_id(cliente, atras, metodo, ruta, servicio):
    cliente.get(ruta)

    assert [r['ruta'] for r in atras[servicio].recibidas] == [ruta]


def test_una_ruta_inexistente_da_404_propio_con_los_grupos(cliente, atras):
    respuesta = cliente.get('/no-existe')

    assert respuesta.status_code == 404
    cuerpo = respuesta.get_json()
    assert cuerpo['error'] == 'Ruta no encontrada'
    grupos = {g['grupo'] for g in cuerpo['grupos_disponibles']}
    assert {'Trabajos', 'Seguimiento', 'Acreditaciones', 'Emparejamiento', 'Sagas'} <= grupos
    assert 'GET /trabajos/{id}' in next(g for g in cuerpo['grupos_disponibles'] if g['grupo'] == 'Trabajos')['rutas']
    assert all(len(s.recibidas) == 0 for s in atras.values())


def test_un_metodo_equivocado_da_405_con_los_metodos_permitidos(cliente):
    respuesta = cliente.delete('/trabajos')

    assert respuesta.status_code == 405
    cuerpo = respuesta.get_json()
    assert cuerpo['error'] == 'Método no permitido'
    assert 'GET' in cuerpo['metodos_permitidos']
    assert 'POST' in cuerpo['metodos_permitidos']
    assert 'DELETE' not in cuerpo['metodos_permitidos']
