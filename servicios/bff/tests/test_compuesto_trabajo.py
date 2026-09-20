"""GET /trabajos/{id}/completo (CA-2.8, CA-2.9, FR-013, FR-017…FR-019)."""
import time

TRABAJO = {'id': 't1', 'estado': 'CREADO', 'categoria': 'PLOMERIA'}
SEGUIMIENTO = {'trabajo_id': 't1', 'prioridad': 'NORMAL'}
EMPAREJAMIENTO = {'trabajo_id': 't1', 'candidatos': ['p1']}
SAGA = {'trabajo_id': 't1', 'estado': 'COMPLETADA'}


def _todo_arriba(atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos/t1', 200, TRABAJO)
    atras['operaciones'].responder('GET', '/seguimientos/t1', 200, SEGUIMIENTO)
    atras['emparejamiento'].responder('GET', '/emparejamientos/t1', 200, EMPAREJAMIENTO)
    atras['saga-log'].responder('GET', '/sagas/t1', 200, SAGA)


def test_con_todo_arriba_devuelve_las_cuatro_partes_tal_cual(cliente, atras):
    _todo_arriba(atras)

    respuesta = cliente.get('/trabajos/t1/completo')

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo['trabajo_id'] == 't1'
    assert cuerpo['correlation_id'] == respuesta.headers['X-Correlation-Id']
    assert cuerpo['partes'] == {
        'trabajo': {'estado': 'DISPONIBLE', 'datos': {'id': 't1', 'estado': 'CREADO', 'categoria': 'PLOMERIA'}},
        'seguimiento': {'estado': 'DISPONIBLE', 'datos': {'trabajo_id': 't1', 'prioridad': 'NORMAL'}},
        'emparejamiento': {'estado': 'DISPONIBLE', 'datos': {'trabajo_id': 't1', 'candidatos': ['p1']}},
        'saga': {'estado': 'DISPONIBLE', 'datos': {'trabajo_id': 't1', 'estado': 'COMPLETADA'}},
    }


def test_con_operaciones_caido_devuelve_lo_que_pudo_y_marca_lo_que_falta(cliente, atras):
    _todo_arriba(atras)
    atras['operaciones'].detener()

    respuesta = cliente.get('/trabajos/t1/completo')

    assert respuesta.status_code == 200
    partes = respuesta.get_json()['partes']
    assert partes['seguimiento'] == {
        'estado': 'NO_DISPONIBLE', 'servicio': 'operaciones', 'motivo': 'CONEXION_RECHAZADA',
    }
    assert [partes[p]['estado'] for p in ('trabajo', 'emparejamiento', 'saga')] == ['DISPONIBLE'] * 3


def test_un_trabajo_recien_creado_es_todavia_no_disponible_y_no_un_404(cliente, atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos/t1', 200, TRABAJO)
    for servicio, ruta in (('operaciones', '/seguimientos/t1'), ('emparejamiento', '/emparejamientos/t1'), ('saga-log', '/sagas/t1')):
        atras[servicio].responder('GET', ruta, 404, {'error': 'todavia no'})

    respuesta = cliente.get('/trabajos/t1/completo')

    assert respuesta.status_code == 200
    partes = respuesta.get_json()['partes']
    assert partes['trabajo']['estado'] == 'DISPONIBLE'
    assert partes['seguimiento'] == {'estado': 'TODAVIA_NO_DISPONIBLE'}
    assert partes['emparejamiento'] == {'estado': 'TODAVIA_NO_DISPONIBLE'}
    assert partes['saga'] == {'estado': 'TODAVIA_NO_DISPONIBLE'}


def test_si_el_trabajo_no_existe_el_404_llega_tal_cual_y_sin_partes(cliente, atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos/t1', 404, b'{"error": "Trabajo no encontrado"}')

    respuesta = cliente.get('/trabajos/t1/completo')

    assert respuesta.status_code == 404
    assert respuesta.data == b'{"error": "Trabajo no encontrado"}'
    assert b'partes' not in respuesta.data


def test_con_todos_los_servicios_caidos_da_503_con_los_nombres(cliente, atras):
    for servidor in atras.values():
        servidor.detener()

    respuesta = cliente.get('/trabajos/t1/completo')

    assert respuesta.status_code == 503
    cuerpo = respuesta.get_json()
    assert sorted(cuerpo['servicio']) == ['emparejamiento', 'gestion-trabajos', 'operaciones', 'saga-log']
    assert cuerpo['correlation_id'] == respuesta.headers['X-Correlation-Id']


def test_una_parte_con_5xx_queda_no_disponible_por_error_interno(cliente, atras):
    _todo_arriba(atras)
    atras['emparejamiento'].responder('GET', '/emparejamientos/t1', 500, b'Traceback ...', tipo='text/plain')

    respuesta = cliente.get('/trabajos/t1/completo')

    assert respuesta.status_code == 200
    assert respuesta.get_json()['partes']['emparejamiento'] == {
        'estado': 'NO_DISPONIBLE', 'servicio': 'emparejamiento', 'motivo': 'ERROR_INTERNO_UPSTREAM',
    }
    assert b'Traceback' not in respuesta.data


def test_una_respuesta_inesperada_de_una_parte_no_tumba_la_respuesta(cliente, atras):
    _todo_arriba(atras)
    atras['operaciones'].responder('GET', '/seguimientos/t1', 422, b'{"error": "x"}')
    atras['saga-log'].responder('GET', '/sagas/t1', 200, b'esto no es json', tipo='text/plain')

    respuesta = cliente.get('/trabajos/t1/completo')

    assert respuesta.status_code == 200
    partes = respuesta.get_json()['partes']
    assert partes['seguimiento'] == {'estado': 'NO_DISPONIBLE', 'servicio': 'operaciones', 'motivo': 'RESPUESTA_INESPERADA'}
    assert partes['saga'] == {'estado': 'NO_DISPONIBLE', 'servicio': 'saga-log', 'motivo': 'RESPUESTA_INESPERADA'}


def test_las_llamadas_se_hacen_en_paralelo(hacer_app, atras):
    _todo_arriba(atras)
    for servicio, ruta, cuerpo in (
        ('gestion-trabajos', '/trabajos/t1', TRABAJO),
        ('operaciones', '/seguimientos/t1', SEGUIMIENTO),
        ('emparejamiento', '/emparejamientos/t1', EMPAREJAMIENTO),
        ('saga-log', '/sagas/t1', SAGA),
    ):
        atras[servicio].responder('GET', ruta, 200, cuerpo, demora_s=0.5)
    cliente = hacer_app(TIMEOUT_COMPUESTO_S=2).test_client()

    inicio = time.perf_counter()
    respuesta = cliente.get('/trabajos/t1/completo')
    duracion = time.perf_counter() - inicio

    assert respuesta.status_code == 200
    assert duracion < 1.2  # en secuencia serían >= 2 s


def test_el_identificador_de_correlacion_llega_a_los_hilos(cliente, atras):
    _todo_arriba(atras)

    respuesta = cliente.get('/trabajos/t1/completo', headers={'X-Correlation-Id': 'cid-hilos-1'})

    assert respuesta.headers['X-Correlation-Id'] == 'cid-hilos-1'
    recibidas = [
        atras[s].recibidas[-1]['cabeceras']['x-correlation-id']
        for s in ('gestion-trabajos', 'operaciones', 'emparejamiento', 'saga-log')
    ]
    assert recibidas == ['cid-hilos-1'] * 4


def test_sin_cabecera_los_servicios_reciben_el_mismo_identificador_que_devuelve_el_bff(cliente, atras):
    _todo_arriba(atras)

    respuesta = cliente.get('/trabajos/t1/completo')

    devuelto = respuesta.headers['X-Correlation-Id']
    assert len(devuelto) == 36
    recibidas = {atras[s].recibidas[-1]['cabeceras']['x-correlation-id'] for s in ('gestion-trabajos', 'operaciones')}
    assert recibidas == {devuelto}
