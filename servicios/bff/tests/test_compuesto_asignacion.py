"""POST /trabajos/asignacion (FR-016, CA-2.17b)."""
import json

CUERPO = b'{"categoria": "PLOMERIA", "pais": "CO", "ciudad": "Bogota"}'


def test_un_202_trae_el_identificador_y_las_direcciones_de_seguimiento(cliente, atras):
    atras['gestion-trabajos'].responder('POST', '/trabajos', 202, {'id': 'b3f1', 'estado': 'CREADO'})

    respuesta = cliente.post('/trabajos/asignacion', data=CUERPO, content_type='application/json')

    assert respuesta.status_code == 202
    cuerpo = respuesta.get_json()
    assert cuerpo['id'] == 'b3f1'
    assert cuerpo['estado'] == 'CREADO'
    assert cuerpo['correlation_id'] == respuesta.headers['X-Correlation-Id']
    assert cuerpo['seguimiento_saga'] == '/sagas/b3f1'
    assert cuerpo['seguimiento_completo'] == '/trabajos/b3f1/completo'
    recibida = atras['gestion-trabajos'].recibidas[-1]
    assert recibida['ruta'] == '/trabajos'
    assert recibida['cuerpo'] == CUERPO


def test_respeta_el_identificador_que_manda_el_cliente(cliente, atras):
    atras['gestion-trabajos'].responder('POST', '/trabajos', 202, {'id': 'b3f1', 'estado': 'CREADO'})

    respuesta = cliente.post(
        '/trabajos/asignacion', data=CUERPO, content_type='application/json',
        headers={'X-Correlation-Id': 'cid-cliente-9'},
    )

    assert respuesta.get_json()['correlation_id'] == 'cid-cliente-9'
    assert atras['gestion-trabajos'].recibidas[-1]['cabeceras']['x-correlation-id'] == 'cid-cliente-9'


def test_un_400_llega_con_los_mismos_bytes_y_sin_campos_extra(cliente, atras):
    atras['gestion-trabajos'].responder('POST', '/trabajos', 400, b'{"error": "categoria no permitida en MX"}')

    respuesta = cliente.post('/trabajos/asignacion', data=CUERPO, content_type='application/json')

    assert respuesta.status_code == 400
    assert respuesta.data == b'{"error": "categoria no permitida en MX"}'
    assert 'correlation_id' not in json.loads(respuesta.data)


def test_con_gestion_de_trabajos_caido_da_503_que_lo_nombra(cliente, atras):
    atras['gestion-trabajos'].detener()

    respuesta = cliente.post('/trabajos/asignacion', data=CUERPO, content_type='application/json')

    assert respuesta.status_code == 503
    assert respuesta.get_json()['servicio'] == 'gestion-trabajos'


def test_un_202_que_no_es_un_objeto_json_pasa_sin_modificar(cliente, atras):
    atras['gestion-trabajos'].responder('POST', '/trabajos', 202, b'aceptado', tipo='text/plain')

    respuesta = cliente.post('/trabajos/asignacion', data=CUERPO, content_type='application/json')

    assert respuesta.status_code == 202
    assert respuesta.data == b'aceptado'
