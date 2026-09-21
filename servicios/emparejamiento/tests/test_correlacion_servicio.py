"""El identificador de correlación en Emparejamiento (CA-2.17c, CA-2.19, CA-2.20, CA-2.21,
FR-027…FR-031): entra por el borde, sale por el borde y no toca el dominio.

Sin broker: el productor y el cliente de Pulsar se simulan, pero el camino que se
ejercita es el real (handler → mapeador → despachador; bucle `correr`).
"""
import contextvars
import logging
import re
from types import SimpleNamespace

import pytest

from emparejamiento import consumidor, crear_app
from emparejamiento.modulos.emparejamiento.aplicacion.handlers import HandlerEmparejamientoIntegracion
from emparejamiento.modulos.emparejamiento.dominio.eventos import CandidatosIdentificados, SinCandidatos
from emparejamiento.modulos.emparejamiento.infraestructura import consumidores as consumidores_modulo
from emparejamiento.modulos.emparejamiento.infraestructura.mapeadores import MapeadorEmparejamientoIntegracion
from emparejamiento.modulos.emparejamiento.infraestructura.schema.v1.evt_emparejamiento import EventoEmparejamiento
from emparejamiento.modulos.emparejamiento.infraestructura.schema.v1.evt_trabajo import TIPO_CREADO
from emparejamiento.seedwork.infraestructura import correlacion, despachadores

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
    falso = _ConsumidorFalso(mensajes)
    monkeypatch.setattr(consumidor, 'cliente', lambda: SimpleNamespace(subscribe=lambda *a, **k: falso))

    def ejecutar():
        with pytest.raises(_Parar):
            consumidor.correr('topico', 'suscripcion', EventoEmparejamiento, manejar)
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


# ------------------------------------------------------------------ publicación

def test_el_despachador_fija_la_correlacion_y_deja_intacta_la_clave_de_particion(monkeypatch):
    productor = _ProductorFalso()
    monkeypatch.setattr(despachadores, 'productor', lambda topico, schema: productor)

    def caso():
        with correlacion.contexto('cid-literal-1'):
            despachadores.Despachador()._publicar_mensaje(
                'mensaje', 'topico-x', None, 'trabajo-123', {'region': 'andina', 'correlation_id': 'otro-valor'},
            )

    contextvars.copy_context().run(caso)

    assert productor.enviados == [{
        'mensaje': 'mensaje',
        'partition_key': 'trabajo-123',
        'properties': {'region': 'andina', 'correlation_id': 'cid-literal-1'},
    }]


@pytest.mark.parametrize('evento', [
    CandidatosIdentificados(trabajo_id='trabajo-999', region='andina', categoria='PLOMERIA', pais='CO',
                            ciudad='Bogota', proveedores_id=['p1']),
    SinCandidatos(trabajo_id='trabajo-999', region='andina', categoria='PLOMERIA', pais='CO', ciudad='Bogota'),
], ids=['candidatos', 'sin-candidatos'])
def test_el_sobre_lleva_la_correlacion_y_no_el_id_del_trabajo(evento):
    def caso():
        with correlacion.contexto('cid-literal-1'):
            mensaje, _ = MapeadorEmparejamientoIntegracion().entidad_a_dto(evento)
            return mensaje.correlation_id

    resultado = contextvars.copy_context().run(caso)

    assert resultado == 'cid-literal-1'
    assert resultado != 'trabajo-999'


def test_un_evento_real_sale_con_la_misma_correlacion_en_el_sobre_y_en_las_propiedades(monkeypatch):
    productor = _ProductorFalso()
    monkeypatch.setattr(despachadores, 'productor', lambda topico, schema: productor)
    monkeypatch.setattr(despachadores.Despachador, 'publicar_evento', PUBLICAR_EVENTO_REAL)
    evento = SinCandidatos(trabajo_id='trabajo-123', region='andina', categoria='PLOMERIA', pais='CO', ciudad='Bogota')

    def caso():
        with correlacion.contexto('cid-literal-1'):
            HandlerEmparejamientoIntegracion.publicar(evento)

    contextvars.copy_context().run(caso)

    enviado, = productor.enviados
    assert enviado['mensaje'].correlation_id == 'cid-literal-1'
    assert enviado['properties'] == {'correlation_id': 'cid-literal-1', 'region': 'andina'}
    assert enviado['partition_key'] == 'trabajo-123'


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

    falso = _correr(monkeypatch, [mensaje], fallar)

    assert falso.rechazados == [mensaje]
    assert falso.confirmados == []
    errores = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert [r.correlation_id for r in errores] == ['cid-del-sobre']


# ----------------------------------------------------- trabajo_id en los registros

def test_el_evento_de_trabajo_deja_el_trabajo_id_en_el_registro(monkeypatch, caplog):
    correlacion.instalar_registro()
    caplog.set_level(logging.INFO)
    monkeypatch.setenv('REGION', 'andina')
    monkeypatch.setattr(consumidores_modulo, 'ejecutar_comando', lambda comando: None)
    valor = SimpleNamespace(type=TIPO_CREADO, trabajo_id='t-888', categoria='PLOMERIA', pais='CO', ciudad='Bogota')

    def caso():
        with correlacion.contexto('cid-literal-1'):
            consumidores_modulo.manejar_evento_trabajo(valor, _Mensaje(valor))

    contextvars.copy_context().run(caso)

    procesado, = [r for r in caplog.records if r.getMessage().startswith('evt-trabajo procesado')]
    assert procesado.campos == ' trabajo_id=t-888'
    assert procesado.correlation_id == 'cid-literal-1'


def test_el_evento_de_acreditacion_no_fija_trabajo_id(monkeypatch, caplog):
    correlacion.instalar_registro()
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(consumidores_modulo, 'ejecutar_comando', lambda comando: None)
    valor = SimpleNamespace(
        proveedor_id='p1', pais='CO', ciudad='Bogota', categorias=['PLOMERIA'], nivel='ORO',
        estado='ACREDITADA', vigente_hasta='2027-01-01', version=1,
    )

    def caso():
        with correlacion.contexto('cid-literal-1'):
            consumidores_modulo.manejar_evento_acreditacion(valor, None)

    contextvars.copy_context().run(caso)

    procesado, = [r for r in caplog.records if r.getMessage().startswith('evt-acreditacion procesado')]
    assert procesado.campos == ''


def test_una_ruta_de_emparejamiento_escribe_el_trabajo_id_en_las_lineas_de_registro():
    app = crear_app({'TESTING': True})
    registros = []

    class _Captura(logging.Handler):
        def emit(self, registro):
            registros.append(registro)

    @app.after_request
    def _durante_la_peticion(respuesta):
        logging.getLogger('prueba-emp').warning('dentro de la peticion')
        return respuesta

    logger = logging.getLogger('prueba-emp')
    manejador = _Captura(level=logging.WARNING)
    logger.addHandler(manejador)
    try:
        with app.app_context():
            app.test_client().get('/emparejamientos/t-777', headers={'X-Correlation-Id': 'cid-ruta-1'})
    finally:
        logger.removeHandler(manejador)

    assert [r.campos for r in registros] == [' trabajo_id=t-777']
    assert [r.correlation_id for r in registros] == ['cid-ruta-1']


def test_candidatos_no_tiene_id_de_trabajo_y_no_escribe_el_campo():
    app = crear_app({'TESTING': True})
    registros = []

    class _Captura(logging.Handler):
        def emit(self, registro):
            registros.append(registro)

    @app.after_request
    def _durante_la_peticion(respuesta):
        logging.getLogger('prueba-emp2').warning('dentro de la peticion')
        return respuesta

    logger = logging.getLogger('prueba-emp2')
    manejador = _Captura(level=logging.WARNING)
    logger.addHandler(manejador)
    try:
        with app.app_context():
            app.test_client().get('/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota')
    finally:
        logger.removeHandler(manejador)

    assert [r.campos for r in registros] == ['']
