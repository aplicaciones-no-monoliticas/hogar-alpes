"""Fallos del servicio de atrás (CA-2.14, CA-2.15, FR-010…FR-012)."""
import socket
import time

import pytest

from bff import cliente as cliente_http

RUTA_CANDIDATOS = '/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota'


def test_un_servicio_detenido_da_503_que_lo_nombra(cliente, atras):
    atras['operaciones'].detener()

    respuesta = cliente.get('/seguimientos/x')

    assert respuesta.status_code == 503
    cuerpo = respuesta.get_json()
    assert cuerpo['servicio'] == 'operaciones'
    assert cuerpo['motivo'] == 'CONEXION_RECHAZADA'
    assert 'operaciones' in cuerpo['error']
    assert cuerpo['correlation_id'] == respuesta.headers['X-Correlation-Id']


def test_un_servicio_lento_da_503_por_tiempo_limite(hacer_app, atras):
    atras['operaciones'].responder('GET', '/seguimientos/x', 200, {'ok': True}, demora_s=1.5)
    cliente = hacer_app(TIMEOUT_REENVIO_S=0.3).test_client()

    inicio = time.perf_counter()
    respuesta = cliente.get('/seguimientos/x')
    duracion = time.perf_counter() - inicio

    assert respuesta.status_code == 503
    assert respuesta.get_json()['motivo'] == 'TIMEOUT'
    assert respuesta.get_json()['servicio'] == 'operaciones'
    assert duracion < 0.3 + 1


def test_un_servicio_que_no_resuelve_da_503_por_dns(hacer_app):
    cliente = hacer_app(URL_OPERACIONES='http://servicio-que-no-existe.invalid:5000').test_client()

    respuesta = cliente.get('/seguimientos/x')

    assert respuesta.status_code == 503
    assert respuesta.get_json()['motivo'] == 'DNS'
    assert respuesta.get_json()['servicio'] == 'operaciones'


def test_un_5xx_del_servicio_da_502_sin_reenviar_su_cuerpo(cliente, atras):
    atras['operaciones'].responder(
        'GET', '/seguimientos/x', 500, b'Traceback (most recent call last): ...', tipo='text/plain',
    )

    respuesta = cliente.get('/seguimientos/x')

    assert respuesta.status_code == 502
    cuerpo = respuesta.get_json()
    assert cuerpo['servicio'] == 'operaciones'
    assert cuerpo['status_upstream'] == 500
    assert b'Traceback' not in respuesta.data
    assert b'most recent call' not in respuesta.data


def test_un_4xx_de_negocio_no_se_traduce(cliente, atras):
    atras['operaciones'].responder('GET', '/seguimientos/x', 422, b'{"error": "x"}')

    respuesta = cliente.get('/seguimientos/x')

    assert respuesta.status_code == 422
    assert respuesta.data == b'{"error": "x"}'


def test_con_un_servicio_caido_las_rutas_de_los_demas_siguen_funcionando(cliente, atras):
    atras['operaciones'].detener()
    atras['emparejamiento'].responder('GET', '/candidatos', 200, [{'proveedor_id': 'p1'}])

    caida = cliente.get('/seguimientos/x')
    viva = cliente.get(RUTA_CANDIDATOS)

    assert caida.status_code == 503
    assert viva.status_code == 200
    assert viva.get_json() == [{'proveedor_id': 'p1'}]


def test_un_error_interno_del_bff_da_500_sin_traza(cliente, monkeypatch):
    def explotar(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(cliente_http, 'llamar', explotar)

    respuesta = cliente.get('/trabajos/abc')

    assert respuesta.status_code == 500
    cuerpo = respuesta.get_json()
    assert cuerpo['error'] == 'Error interno del BFF'
    assert cuerpo['correlation_id'] == respuesta.headers['X-Correlation-Id']
    assert b'boom' not in respuesta.data
    assert b'Traceback' not in respuesta.data


@pytest.mark.parametrize('ruta, servicio', [
    ('/trabajos/abc', 'gestion-trabajos'),
    ('/seguimientos/abc', 'operaciones'),
    ('/acreditaciones/abc', 'acreditacion'),
    ('/emparejamientos/abc', 'emparejamiento'),
])
def test_ninguna_respuesta_de_fallo_trae_traza(cliente, atras, ruta, servicio):
    atras[servicio].detener()

    respuesta = cliente.get(ruta)

    assert respuesta.status_code == 503
    assert b'Traceback' not in respuesta.data


def _dns_lento(*args, **kwargs):
    time.sleep(2)
    raise socket.gaierror('no resuelve')


def test_un_dns_lento_no_pasa_del_tiempo_limite_del_reenvio(hacer_app, monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', _dns_lento)
    cliente = hacer_app(TIMEOUT_REENVIO_S=0.3).test_client()

    inicio = time.perf_counter()
    respuesta = cliente.get('/seguimientos/x')
    duracion = time.perf_counter() - inicio

    assert respuesta.status_code == 503
    assert respuesta.get_json()['servicio'] == 'operaciones'
    assert respuesta.get_json()['motivo'] == 'TIMEOUT'
    assert duracion < 1.0


def test_un_dns_lento_no_pasa_del_tiempo_limite_de_un_compuesto(hacer_app, monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', _dns_lento)
    cliente = hacer_app(TIMEOUT_COMPUESTO_S=0.3).test_client()

    inicio = time.perf_counter()
    respuesta = cliente.get('/estado-del-sistema')
    duracion = time.perf_counter() - inicio

    assert respuesta.status_code == 200
    assert respuesta.get_json()['estado_general'] == 'DEGRADADO'
    assert duracion < 1.0
