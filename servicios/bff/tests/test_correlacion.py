"""Identificador de correlación en el BFF (CA-2.16, CA-2.17, CA-2.17b, FR-023…FR-026, FR-028b)."""
import logging
import re

import pytest

from bff import cliente as cliente_http

UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
CUERPO = b'{"categoria": "PLOMERIA", "pais": "CO", "ciudad": "Bogota"}'


def _crear_trabajo(cliente, **kwargs):
    return cliente.post('/trabajos', data=CUERPO, content_type='application/json', **kwargs)


def test_sin_cabecera_la_respuesta_trae_un_uuid(cliente, atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos/abc', 200, {'id': 'abc'})

    respuesta = cliente.get('/trabajos/abc')

    assert UUID.match(respuesta.headers['X-Correlation-Id'])


def test_con_cabecera_valida_la_respeta_y_se_la_manda_al_servicio(cliente, atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos/abc', 200, {'id': 'abc'})

    respuesta = cliente.get('/trabajos/abc', headers={'X-Correlation-Id': 'mi-id-de-prueba'})

    assert respuesta.headers['X-Correlation-Id'] == 'mi-id-de-prueba'
    assert atras['gestion-trabajos'].recibidas[-1]['cabeceras']['x-correlation-id'] == 'mi-id-de-prueba'


@pytest.mark.parametrize('invalido', ['', 'a' * 65, 'con espacios y | raros', 'x=y'])
def test_una_cabecera_invalida_se_reemplaza_por_un_uuid(cliente, atras, invalido):
    atras['gestion-trabajos'].responder('GET', '/trabajos/abc', 200, {'id': 'abc'})

    respuesta = cliente.get('/trabajos/abc', headers={'X-Correlation-Id': invalido})

    devuelto = respuesta.headers['X-Correlation-Id']
    assert devuelto != invalido
    assert UUID.match(devuelto)
    assert atras['gestion-trabajos'].recibidas[-1]['cabeceras']['x-correlation-id'] == devuelto


def _caso_202(cliente, atras, monkeypatch):
    atras['gestion-trabajos'].responder('POST', '/trabajos', 202, {'id': 'abc', 'estado': 'CREADO'})
    return _crear_trabajo(cliente)


def _caso_400(cliente, atras, monkeypatch):
    atras['gestion-trabajos'].responder('POST', '/trabajos', 400, {'error': 'categoria no permitida en MX'})
    return _crear_trabajo(cliente)


def _caso_404_servicio(cliente, atras, monkeypatch):
    atras['operaciones'].responder('GET', '/seguimientos/x', 404, {'error': 'no existe'})
    return cliente.get('/seguimientos/x')


def _caso_404_propio(cliente, atras, monkeypatch):
    return cliente.get('/no-existe')


def _caso_405(cliente, atras, monkeypatch):
    return cliente.delete('/trabajos')


def _caso_502(cliente, atras, monkeypatch):
    atras['operaciones'].responder('GET', '/seguimientos/x', 500, b'boom', tipo='text/plain')
    return cliente.get('/seguimientos/x')


def _caso_503(cliente, atras, monkeypatch):
    atras['operaciones'].detener()
    return cliente.get('/seguimientos/x')


def _caso_500(cliente, atras, monkeypatch):
    def explotar(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(cliente_http, 'llamar', explotar)
    return cliente.get('/trabajos/abc')


@pytest.mark.parametrize('caso, codigo', [
    (_caso_202, 202), (_caso_400, 400), (_caso_404_servicio, 404), (_caso_404_propio, 404),
    (_caso_405, 405), (_caso_502, 502), (_caso_503, 503), (_caso_500, 500),
])
def test_la_cabecera_esta_en_toda_respuesta_incluidas_las_de_error(cliente, atras, monkeypatch, caso, codigo):
    respuesta = caso(cliente, atras, monkeypatch)

    assert respuesta.status_code == codigo
    assert UUID.match(respuesta.headers['X-Correlation-Id'])


def test_un_202_de_post_trabajos_trae_el_identificador_en_el_cuerpo(cliente, atras, monkeypatch):
    respuesta = _caso_202(cliente, atras, monkeypatch)

    cuerpo = respuesta.get_json()
    assert cuerpo['correlation_id'] == respuesta.headers['X-Correlation-Id']
    assert cuerpo['id'] == 'abc'
    assert cuerpo['estado'] == 'CREADO'


def test_un_error_de_post_trabajos_llega_con_los_mismos_bytes_y_sin_el_campo(cliente, atras, monkeypatch):
    respuesta = _caso_400(cliente, atras, monkeypatch)

    assert respuesta.data == b'{"error": "categoria no permitida en MX"}'


def test_los_demas_reenvios_no_agregan_el_campo(cliente, atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos/abc', 200, b'{"id": "abc"}')

    respuesta = cliente.get('/trabajos/abc')

    assert respuesta.data == b'{"id": "abc"}'


def _linea_de_peticion(caplog):
    lineas = [r for r in caplog.records if r.name == 'bff.peticion']
    assert len(lineas) == 1
    return lineas[0]


def test_la_linea_de_registro_por_peticion_lleva_el_identificador_y_los_datos(cliente, atras, caplog):
    atras['gestion-trabajos'].responder('GET', '/trabajos/t-777', 200, {'id': 't-777'})
    caplog.set_level(logging.INFO)

    respuesta = cliente.get('/trabajos/t-777')

    linea = _linea_de_peticion(caplog)
    assert linea.correlation_id == respuesta.headers['X-Correlation-Id']
    assert re.fullmatch(r'GET /trabajos/t-777 -> gestion-trabajos 200 \d+ms', linea.getMessage())


def test_la_linea_de_una_ruta_propia_no_nombra_servicio_destino(cliente, caplog):
    caplog.set_level(logging.INFO)

    cliente.get('/no-existe')

    assert re.fullmatch(r'GET /no-existe -> - 404 \d+ms', _linea_de_peticion(caplog).getMessage())


def test_un_id_con_saltos_de_linea_no_parte_la_linea_de_registro(cliente, atras, caplog):
    atras['gestion-trabajos'].responder('GET', '/trabajos/a%0D%0Ab', 200, {'id': 'x'})
    caplog.set_level(logging.INFO)

    cliente.get('/trabajos/a%0D%0Ab')

    mensaje = _linea_de_peticion(caplog).getMessage()
    assert '\n' not in mensaje
    assert '\r' not in mensaje
    assert mensaje.startswith('GET /trabajos/a%0D%0Ab -> gestion-trabajos 200 ')


@pytest.mark.parametrize('ruta, servicio', [('/trabajos/t-777', 'gestion-trabajos'), ('/seguimientos/t-777', 'operaciones')])
def test_las_rutas_con_id_de_trabajo_lo_escriben_en_el_registro(cliente, atras, caplog, ruta, servicio):
    atras[servicio].responder('GET', ruta, 200, {'ok': True})
    caplog.set_level(logging.INFO)

    cliente.get(ruta)

    assert _linea_de_peticion(caplog).campos == ' trabajo_id=t-777'


def test_una_ruta_de_acreditacion_no_escribe_trabajo_id(cliente, atras, caplog):
    atras['acreditacion'].responder('GET', '/acreditaciones/a-1', 200, {'ok': True})
    caplog.set_level(logging.INFO)

    cliente.get('/acreditaciones/a-1')

    assert _linea_de_peticion(caplog).campos == ''


def test_post_trabajos_escribe_el_id_que_devolvio_el_servicio(cliente, atras, caplog, monkeypatch):
    caplog.set_level(logging.INFO)

    _caso_202(cliente, atras, monkeypatch)

    assert _linea_de_peticion(caplog).campos == ' trabajo_id=abc'


def test_post_trabajos_con_error_no_escribe_trabajo_id(cliente, atras, caplog, monkeypatch):
    caplog.set_level(logging.INFO)

    _caso_400(cliente, atras, monkeypatch)

    assert _linea_de_peticion(caplog).campos == ''


def test_asignacion_escribe_el_id_que_devolvio_el_servicio(cliente, atras, caplog):
    atras['gestion-trabajos'].responder('POST', '/trabajos', 202, {'id': 'abc', 'estado': 'CREADO'})
    caplog.set_level(logging.INFO)

    cliente.post('/trabajos/asignacion', data=CUERPO, content_type='application/json')

    assert _linea_de_peticion(caplog).campos == ' trabajo_id=abc'


def test_el_compuesto_de_trabajo_escribe_el_id_del_trabajo(cliente, atras, caplog):
    atras['gestion-trabajos'].responder('GET', '/trabajos/t-777', 200, {'id': 't-777'})
    caplog.set_level(logging.INFO)

    cliente.get('/trabajos/t-777/completo')

    linea = _linea_de_peticion(caplog)
    assert linea.campos == ' trabajo_id=t-777'
    assert linea.getMessage().startswith('GET /trabajos/t-777/completo -> compuesto 200 ')
