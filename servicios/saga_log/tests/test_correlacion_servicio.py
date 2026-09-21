"""El identificador de correlación en `saga_log` (T044, mismo patrón que los
otros cuatro servicios). A diferencia de ellos, este servicio nunca publica
nada (CA-1.16): no hay pruebas de despachador, solo de borde HTTP y de consumo.
"""
import contextvars
import logging
import re
from types import SimpleNamespace

import pytest

from saga_log import consumidor, crear_app
from saga_log.modulos.sagas.infraestructura.schema.v1.evt_trabajo import EventoTrabajo
from saga_log.seedwork.infraestructura import correlacion

UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class _Parar(BaseException):
    """Sale del bucle infinito de `correr`; no es `Exception`, así que no lo atrapa."""


class _Mensaje:
    def __init__(self, valor, propiedades=None):
        self._valor = valor
        self._propiedades = propiedades or {}
        self.llamadas_a_value = 0

    def value(self):
        self.llamadas_a_value += 1
        return self._valor

    def properties(self):
        return self._propiedades


class _ConsumidorFalso:
    def __init__(self, mensajes):
        self.pendientes = list(mensajes)
        self.confirmados = []
        self.rechazados = []

    def receive(self):
        if not self.pendientes:
            raise _Parar()
        return self.pendientes.pop(0)

    def acknowledge(self, mensaje):
        self.confirmados.append(mensaje)

    def negative_acknowledge(self, mensaje):
        self.rechazados.append(mensaje)

    def close(self):
        pass


def _correr(monkeypatch, mensajes, manejar, schema=EventoTrabajo):
    falso = _ConsumidorFalso(mensajes)
    monkeypatch.setattr(consumidor, 'cliente', lambda: SimpleNamespace(subscribe=lambda *a, **k: falso))

    def ejecutar():
        with pytest.raises(_Parar):
            consumidor.correr('topico', 'suscripcion', schema, manejar)
        return correlacion.correlation_id_var.get()

    restaurado = contextvars.copy_context().run(ejecutar)
    assert restaurado is None
    return falso


# ------------------------------------------------------------------ gancho HTTP

def test_la_api_devuelve_un_uuid_si_no_llega_cabecera():
    respuesta = crear_app({'TESTING': True}).test_client().get('/health')

    assert UUID.match(respuesta.headers['X-Correlation-Id'])


def test_la_api_respeta_la_cabecera_valida():
    respuesta = crear_app({'TESTING': True}).test_client().get('/health', headers={'X-Correlation-Id': 'abc-1'})

    assert respuesta.headers['X-Correlation-Id'] == 'abc-1'


def test_la_api_reemplaza_una_cabecera_invalida():
    respuesta = crear_app({'TESTING': True}).test_client().get(
        '/health', headers={'X-Correlation-Id': 'con espacios | raros'},
    )

    assert respuesta.headers['X-Correlation-Id'] != 'con espacios | raros'
    assert UUID.match(respuesta.headers['X-Correlation-Id'])


# ---------------------------------------------------------------------- consumo

def test_el_consumo_usa_la_correlacion_del_sobre(monkeypatch):
    vistos = []
    _correr(
        monkeypatch,
        [_Mensaje(SimpleNamespace(correlation_id='cid-del-sobre'), {'correlation_id': 'cid-de-prop'})],
        lambda valor, mensaje: vistos.append(correlacion.actual()),
    )

    assert vistos == ['cid-del-sobre']


def test_el_consumo_cae_a_la_propiedad_si_el_sobre_viene_vacio(monkeypatch):
    vistos = []
    _correr(
        monkeypatch,
        [_Mensaje(SimpleNamespace(correlation_id=''), {'correlation_id': 'cid-de-prop'})],
        lambda valor, mensaje: vistos.append(correlacion.actual()),
    )

    assert vistos == ['cid-de-prop']


def test_el_mensaje_se_decodifica_una_sola_vez(monkeypatch):
    mensaje = _Mensaje(SimpleNamespace(correlation_id='cid-del-sobre'))

    _correr(monkeypatch, [mensaje], lambda valor, msg: None)

    assert mensaje.llamadas_a_value == 1


def test_si_el_handler_falla_se_rechaza_el_mensaje_y_el_error_lleva_su_correlacion(monkeypatch, caplog):
    correlacion.instalar_registro()
    caplog.set_level(logging.INFO)
    mensaje = _Mensaje(SimpleNamespace(correlation_id='cid-del-sobre'))

    def fallar(valor, msg):
        raise RuntimeError('boom')

    falso = _correr(monkeypatch, [mensaje], fallar)

    assert falso.rechazados == [mensaje]
    assert falso.confirmados == []
    errores = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert [r.correlation_id for r in errores] == ['cid-del-sobre']


# ----------------------------------------------------- trabajo_id en las rutas

def test_una_ruta_con_id_de_trabajo_lo_escribe_en_las_lineas_de_registro():
    app = crear_app({'TESTING': True})
    registros = []

    class _Captura(logging.Handler):
        def emit(self, registro):
            registros.append(registro)

    @app.after_request
    def _durante_la_peticion(respuesta):
        logging.getLogger('prueba-saga').warning('dentro de la peticion')
        return respuesta

    logger = logging.getLogger('prueba-saga')
    manejador = _Captura(level=logging.WARNING)
    logger.addHandler(manejador)
    try:
        app.test_client().get('/sagas/t-777', headers={'X-Correlation-Id': 'cid-ruta-1'})
    finally:
        logger.removeHandler(manejador)

    assert [r.campos for r in registros] == [' trabajo_id=t-777']
    assert [r.correlation_id for r in registros] == ['cid-ruta-1']
