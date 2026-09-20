"""El identificador de correlación en Gestión de Trabajos (CA-2.17c, CA-2.19, CA-2.20,
CA-2.21, FR-027…FR-031): entra por el borde, sale por el borde y no toca el dominio.

Sin broker: el productor y el cliente de Pulsar se simulan, pero el camino que se
ejercita es el real (handler → mapeador → despachador; bucle `correr`).
"""
import contextvars
import logging
import os
import re
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URI', 'sqlite:///:memory:')
os.environ['ADAPTADOR_TRABAJOS'] = 'memoria'

import pytest  # noqa: E402

from gestion_trabajos import crear_app  # noqa: E402
from gestion_trabajos.modulos.trabajos.aplicacion import handlers  # noqa: E402
from gestion_trabajos.modulos.trabajos.dominio.eventos import TrabajoCreado  # noqa: E402
from gestion_trabajos.modulos.trabajos.infraestructura import consumidores as consumidores_modulo  # noqa: E402
from gestion_trabajos.modulos.trabajos.infraestructura.mapeadores import MapeadorEventosTrabajo  # noqa: E402
from gestion_trabajos.modulos.trabajos.infraestructura.schema.v1.comandos import ComandoCrearTrabajo  # noqa: E402
from gestion_trabajos.seedwork.aplicacion import comandos as comandos_seedwork  # noqa: E402
from gestion_trabajos.seedwork.infraestructura import consumidores, correlacion, despachadores  # noqa: E402

UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

# El conftest anula `publicar_evento` para no necesitar un broker; aquí se quiere el real.
PUBLICAR_EVENTO_REAL = despachadores.Despachador.publicar_evento


class _Parar(BaseException):
    """Sale del bucle infinito de `correr`; no es `Exception`, así que no lo atrapa."""


class _ProductorFalso:
    def __init__(self):
        self.enviados = []

    def send(self, mensaje, partition_key=None, properties=None):
        self.enviados.append({'mensaje': mensaje, 'partition_key': partition_key, 'properties': properties})


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


def _correr(monkeypatch, mensajes, manejar):
    """Corre el bucle real de consumo sobre un cliente simulado y devuelve el consumidor falso."""
    consumidor = _ConsumidorFalso(mensajes)
    monkeypatch.setattr(consumidores, 'cliente', lambda: SimpleNamespace(subscribe=lambda *a, **k: consumidor))

    def ejecutar():
        with pytest.raises(_Parar):
            consumidores.correr('topico', 'suscripcion', ComandoCrearTrabajo, manejar)
        return correlacion.correlation_id_var.get()

    restaurado = contextvars.copy_context().run(ejecutar)
    assert restaurado is None
    return consumidor


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


# ------------------------------------------------------------------ publicación

def test_el_despachador_fija_la_correlacion_y_deja_intacta_la_clave_de_particion(monkeypatch):
    productor = _ProductorFalso()
    monkeypatch.setattr(despachadores, 'productor', lambda topico, schema: productor)

    def caso():
        with correlacion.contexto('cid-literal-1'):
            despachadores.Despachador()._publicar_mensaje(
                'mensaje', 'topico-x', None, 'trabajo-123', {'partner_id': 'p1', 'correlation_id': 'otro-valor'},
            )

    contextvars.copy_context().run(caso)

    assert productor.enviados == [{
        'mensaje': 'mensaje',
        'partition_key': 'trabajo-123',
        'properties': {'partner_id': 'p1', 'correlation_id': 'cid-literal-1'},
    }]


def test_el_sobre_lleva_la_correlacion_y_no_el_id_del_trabajo():
    evento = TrabajoCreado(trabajo_id='trabajo-999')

    def caso():
        with correlacion.contexto('cid-literal-1'):
            return MapeadorEventosTrabajo()._sobre(evento, 'x')['correlation_id']

    resultado = contextvars.copy_context().run(caso)

    assert resultado == 'cid-literal-1'
    assert resultado != 'trabajo-999'


def test_un_evento_real_sale_con_la_misma_correlacion_en_el_sobre_y_en_las_propiedades(monkeypatch):
    productor = _ProductorFalso()
    monkeypatch.setattr(despachadores, 'productor', lambda topico, schema: productor)
    monkeypatch.setattr(despachadores.Despachador, 'publicar_evento', PUBLICAR_EVENTO_REAL)
    evento = TrabajoCreado(trabajo_id='trabajo-999', pais='CO', ciudad='Bogota', partner_id='p1')

    def caso():
        with correlacion.contexto('cid-literal-1'):
            handlers._publicar(evento)

    contextvars.copy_context().run(caso)

    enviado, = productor.enviados
    assert enviado['mensaje'].correlation_id == 'cid-literal-1'
    assert enviado['properties']['correlation_id'] == 'cid-literal-1'
    assert enviado['properties']['partner_id'] == 'p1'
    assert enviado['partition_key'] == 'trabajo-999'


def test_publicar_fija_el_trabajo_id_en_el_registro_antes_de_despachar(monkeypatch):
    vistos = []

    class _DespachadorEspia:
        def publicar_evento(self, *args, **kwargs):
            vistos.append(correlacion.campos_actuales())

    monkeypatch.setattr(handlers, 'Despachador', _DespachadorEspia)

    def caso():
        with correlacion.contexto('cid-literal-1'):
            handlers._publicar(TrabajoCreado(trabajo_id='t-999', pais='CO'))

    contextvars.copy_context().run(caso)

    assert vistos == [{'trabajo_id': 't-999'}]


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


def test_el_consumo_crea_un_identificador_distinto_por_mensaje_si_ninguno_trae(monkeypatch):
    vistos = []
    _correr(
        monkeypatch,
        [_Mensaje(SimpleNamespace(correlation_id=None)), _Mensaje(SimpleNamespace(correlation_id=None))],
        lambda valor, mensaje: vistos.append(correlacion.actual()),
    )

    assert len(vistos) == 2
    assert all(UUID.match(v) for v in vistos)
    assert vistos[0] != vistos[1]


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

    consumidor = _correr(monkeypatch, [mensaje], fallar)

    assert consumidor.rechazados == [mensaje]
    assert consumidor.confirmados == []
    errores = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert [r.correlation_id for r in errores] == ['cid-del-sobre']


def test_un_comando_recibido_deja_el_trabajo_id_en_el_registro(monkeypatch, caplog):
    correlacion.instalar_registro()
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(comandos_seedwork, 'ejecutar_comando', lambda comando: None)
    valor = SimpleNamespace(
        trabajo_id='t-888', canal='MARKETPLACE', partner_id='p1', referencia_externa='r', categoria='PLOMERIA',
        urgencia='NORMAL', pais='CO', ciudad='Bogota', direccion='Cra 7', descripcion='fuga',
    )

    def caso():
        with correlacion.contexto('cid-literal-1'):
            consumidores_modulo._manejar_crear_trabajo(valor, _Mensaje(valor))

    contextvars.copy_context().run(caso)

    recibido, = [r for r in caplog.records if r.getMessage().startswith('Comando recibido')]
    assert recibido.campos == ' trabajo_id=t-888'
    assert recibido.correlation_id == 'cid-literal-1'


# ----------------------------------------------------- trabajo_id en las rutas

def test_una_ruta_con_id_de_trabajo_lo_escribe_en_las_lineas_de_registro():
    app = crear_app({'TESTING': True})
    registros = []

    class _Captura(logging.Handler):
        def emit(self, registro):
            registros.append(registro)

    @app.after_request
    def _durante_la_peticion(respuesta):
        logging.getLogger('prueba-gt').warning('dentro de la peticion')
        return respuesta

    logger = logging.getLogger('prueba-gt')
    manejador = _Captura(level=logging.WARNING)
    logger.addHandler(manejador)
    try:
        app.test_client().get('/trabajos/t-777', headers={'X-Correlation-Id': 'cid-ruta-1'})
    finally:
        logger.removeHandler(manejador)

    assert [r.campos for r in registros] == [' trabajo_id=t-777']
    assert [r.correlation_id for r in registros] == ['cid-ruta-1']
