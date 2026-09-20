"""GET /estado-del-sistema (CA-2.10, FR-015): siempre 200, incluso con todo caído."""

DE_ATRAS = ('gestion-trabajos', 'operaciones', 'acreditacion', 'emparejamiento', 'saga-log')
SEIS = {'bff', 'gestion-trabajos', 'operaciones', 'acreditacion', 'emparejamiento', 'saga-log'}


def _todo_arriba(atras):
    for nombre in DE_ATRAS:
        atras[nombre].responder('GET', '/health', 200, {'status': 'up'})
    atras['saga-log'].responder('GET', '/sagas/resumen', 200, {'COMPLETADA': 3, 'COMPENSADA': 1})


def test_con_todo_arriba_reporta_los_seis_componentes_y_el_resumen_de_sagas(cliente, atras):
    _todo_arriba(atras)

    respuesta = cliente.get('/estado-del-sistema')

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo['estado_general'] == 'OK'
    assert cuerpo['correlation_id'] == respuesta.headers['X-Correlation-Id']
    assert set(cuerpo['componentes']) == SEIS
    assert cuerpo['componentes']['bff'] == {'estado': 'UP'}
    for nombre in DE_ATRAS:
        componente = cuerpo['componentes'][nombre]
        assert set(componente) == {'estado', 'latencia_ms'}
        assert componente['estado'] == 'UP'
        assert isinstance(componente['latencia_ms'], int)
    assert cuerpo['sagas'] == {'estado': 'DISPONIBLE', 'datos': {'COMPLETADA': 3, 'COMPENSADA': 1}}


def test_con_saga_log_caido_queda_degradado_pero_sigue_en_200(cliente, atras):
    _todo_arriba(atras)
    atras['saga-log'].detener()

    respuesta = cliente.get('/estado-del-sistema')

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo['estado_general'] == 'DEGRADADO'
    saga = cuerpo['componentes']['saga-log']
    assert saga['estado'] == 'DOWN'
    assert saga['motivo'] == 'CONEXION_RECHAZADA'
    assert 'latencia_ms' not in saga
    assert cuerpo['sagas'] == {'estado': 'NO_DISPONIBLE', 'servicio': 'saga-log', 'motivo': 'CONEXION_RECHAZADA'}
    assert cuerpo['componentes']['operaciones']['estado'] == 'UP'


def test_con_todos_los_servicios_caidos_sigue_respondiendo_200(cliente, atras):
    for servidor in atras.values():
        servidor.detener()

    respuesta = cliente.get('/estado-del-sistema')

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo['estado_general'] == 'DEGRADADO'
    assert cuerpo['componentes']['bff'] == {'estado': 'UP'}
    assert [cuerpo['componentes'][n]['estado'] for n in DE_ATRAS] == ['DOWN'] * 5


def test_un_health_con_5xx_o_con_otro_codigo_cuenta_como_caido(cliente, atras):
    _todo_arriba(atras)
    atras['operaciones'].responder('GET', '/health', 500, b'boom', tipo='text/plain')
    atras['acreditacion'].responder('GET', '/health', 404, b'{"error": "x"}')

    respuesta = cliente.get('/estado-del-sistema')

    componentes = respuesta.get_json()['componentes']
    assert componentes['operaciones'] == {'estado': 'DOWN', 'motivo': 'ERROR_INTERNO_UPSTREAM'}
    assert componentes['acreditacion'] == {'estado': 'DOWN', 'motivo': 'RESPUESTA_INESPERADA'}
    assert respuesta.get_json()['estado_general'] == 'DEGRADADO'
