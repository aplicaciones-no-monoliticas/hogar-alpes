"""Módulo `correlacion`: identificador de correlación y campos de registro.

Es la prueba de referencia de una pieza que vive en seis copias idénticas
(plantilla, cuatro servicios y BFF). Cada prueba corre en un contexto limpio
para que un valor fijado no se filtre a la siguiente.
"""
import contextvars
import logging
import re
import threading

import pytest
from flask import Flask

from gestion_trabajos.seedwork.infraestructura import correlacion

FORMATO = '%(levelname)s %(name)s | cid=%(correlation_id)s%(campos)s | %(message)s'
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def en_contexto_limpio(funcion):
    """Ejecuta `funcion` en una copia del contexto: lo que fije no se filtra."""
    return contextvars.copy_context().run(funcion)


class _Mensaje:
    def __init__(self, propiedades):
        self._propiedades = propiedades

    def properties(self):
        return self._propiedades


class _Valor:
    def __init__(self, correlation_id):
        self.correlation_id = correlation_id


def _registro(mensaje='hola'):
    return logging.getLogRecordFactory()('x', logging.INFO, __file__, 1, mensaje, None, None)


def _formatear(registro):
    return logging.Formatter(FORMATO).format(registro)


# ---------------------------------------------------------------- normalizar

@pytest.mark.parametrize('valido', ['abc-123_X.y:z', 'a' * 64, 'a', '5d0c9e1e-1111-4222-8333-944455556666'])
def test_normalizar_acepta_la_forma_valida(valido):
    assert correlacion.normalizar(valido) == valido


@pytest.mark.parametrize(
    'invalido',
    ['a' * 65, '', None, 'con espacios', 'x|y', 'x=y', 'x\ny', 'abc\n', 42, b'abc'],
)
def test_normalizar_rechaza_lo_que_no_cumple_la_forma(invalido):
    assert correlacion.normalizar(invalido) is None


# -------------------------------------------------------------------- actual

def test_actual_sin_contexto_crea_un_uuid_y_lo_deja_fijado():
    def caso():
        primero = correlacion.actual()
        segundo = correlacion.actual()
        return primero, segundo

    primero, segundo = en_contexto_limpio(caso)
    assert len(primero) == 36
    assert UUID.match(primero)
    assert segundo == primero


# ------------------------------------------------------------------ contexto

def test_contexto_fija_el_valor_y_lo_restaura_al_salir():
    def caso():
        antes = correlacion.correlation_id_var.get()
        with correlacion.contexto('id-fijo-1') as dentro:
            visto = correlacion.actual()
        return antes, dentro, visto, correlacion.correlation_id_var.get()

    antes, dentro, visto, despues = en_contexto_limpio(caso)
    assert antes is None
    assert dentro == 'id-fijo-1'
    assert visto == 'id-fijo-1'
    assert despues is None


def test_contexto_anidado_restaura_el_valor_exterior():
    def caso():
        vistos = []
        with correlacion.contexto('a'):
            with correlacion.contexto('b'):
                vistos.append(correlacion.actual())
            vistos.append(correlacion.actual())
        return vistos

    assert en_contexto_limpio(caso) == ['b', 'a']


@pytest.mark.parametrize('entrada', ['con espacios', None, '', 'a' * 65])
def test_contexto_con_valor_invalido_genera_uno_nuevo(entrada):
    def caso():
        with correlacion.contexto(entrada) as generado:
            return generado, correlacion.actual()

    generado, visto = en_contexto_limpio(caso)
    assert generado != entrada
    assert UUID.match(generado)
    assert visto == generado


def test_dos_hilos_ven_su_propio_valor():
    vistos = {}
    listo = threading.Barrier(2)

    def hilo(nombre, valor):
        with correlacion.contexto(valor):
            listo.wait(timeout=5)
            vistos[nombre] = correlacion.actual()
            listo.wait(timeout=5)

    hilos = [
        threading.Thread(target=hilo, args=('uno', 'id-uno')),
        threading.Thread(target=hilo, args=('dos', 'id-dos')),
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=10)

    assert vistos == {'uno': 'id-uno', 'dos': 'id-dos'}


# ------------------------------------------------------------- desde_mensaje

def test_desde_mensaje_prefiere_el_campo_del_sobre():
    assert correlacion.desde_mensaje(_Valor('del-sobre'), _Mensaje({'correlation_id': 'de-prop'})) == 'del-sobre'


def test_desde_mensaje_cae_a_la_propiedad_si_el_sobre_no_es_valido():
    assert correlacion.desde_mensaje(_Valor(''), _Mensaje({'correlation_id': 'de-prop'})) == 'de-prop'
    assert correlacion.desde_mensaje(_Valor(None), _Mensaje({'correlation_id': 'de-prop'})) == 'de-prop'
    assert correlacion.desde_mensaje(_Valor('con espacios'), _Mensaje({'correlation_id': 'de-prop'})) == 'de-prop'


def test_desde_mensaje_devuelve_none_si_ninguno_es_valido():
    assert correlacion.desde_mensaje(_Valor(None), _Mensaje({})) is None
    assert correlacion.desde_mensaje(_Valor(''), _Mensaje({'correlation_id': 'x y'})) is None


def test_desde_mensaje_sin_valor_solo_mira_la_propiedad():
    assert correlacion.desde_mensaje(None, _Mensaje({'correlation_id': 'de-prop'})) == 'de-prop'
    assert correlacion.desde_mensaje(None, _Mensaje({})) is None


# ------------------------------------------------------------------ registro

def test_instalar_registro_es_idempotente_y_no_envuelve_dos_veces():
    def caso():
        correlacion.instalar_registro()
        primera = logging.getLogRecordFactory()
        correlacion.instalar_registro()
        return primera, logging.getLogRecordFactory()

    primera, segunda = en_contexto_limpio(caso)
    assert segunda is primera


def test_el_registro_fuera_de_contexto_trae_guion():
    correlacion.instalar_registro()
    registro = en_contexto_limpio(_registro)
    assert registro.correlation_id == '-'
    assert registro.campos == ''


def test_el_registro_dentro_de_contexto_trae_el_identificador():
    correlacion.instalar_registro()

    def caso():
        with correlacion.contexto('id-fijo-1'):
            return _registro()

    assert en_contexto_limpio(caso).correlation_id == 'id-fijo-1'


def test_el_formato_de_la_linea_es_exacto_sin_y_con_campos():
    correlacion.instalar_registro()

    def caso():
        with correlacion.contexto('id-fijo-1'):
            sin_campos = _formatear(_registro())
            correlacion.agregar_campos(trabajo_id='t-1')
            con_campos = _formatear(_registro())
        return sin_campos, con_campos

    sin_campos, con_campos = en_contexto_limpio(caso)
    assert sin_campos == 'INFO x | cid=id-fijo-1 | hola'
    assert con_campos == 'INFO x | cid=id-fijo-1 trabajo_id=t-1 | hola'


# ------------------------------------------------------------ campos de registro

def test_agregar_campos_descarta_valores_y_nombres_invalidos():
    def caso():
        with correlacion.contexto('id-fijo-1'):
            correlacion.agregar_campos(trabajo_id='t-1', otro='x y')
            correlacion.agregar_campos(**{'Trabajo Id': 't-2'})
            return correlacion.campos_actuales()

    assert en_contexto_limpio(caso) == {'trabajo_id': 't-1'}


def test_los_campos_se_restauran_al_salir_del_contexto():
    def caso():
        with correlacion.contexto('id-fijo-1'):
            correlacion.agregar_campos(trabajo_id='t-1')
        return correlacion.campos_actuales()

    assert en_contexto_limpio(caso) == {}


def test_agregar_campos_fuera_de_un_contexto_no_hace_nada():
    def caso():
        correlacion.agregar_campos(trabajo_id='t-1')
        return correlacion.campos_actuales()

    assert en_contexto_limpio(caso) == {}


def test_dos_hilos_no_ven_los_campos_del_otro():
    vistos = {}
    listo = threading.Barrier(2)

    def hilo(nombre, trabajo):
        with correlacion.contexto(f'cid-{nombre}'):
            correlacion.agregar_campos(trabajo_id=trabajo)
            listo.wait(timeout=5)
            vistos[nombre] = correlacion.campos_actuales()
            listo.wait(timeout=5)

    hilos = [
        threading.Thread(target=hilo, args=('uno', 't-1')),
        threading.Thread(target=hilo, args=('dos', 't-2')),
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=10)

    assert vistos == {'uno': {'trabajo_id': 't-1'}, 'dos': {'trabajo_id': 't-2'}}


# --------------------------------------------------------------------- Flask

def _app(campos_ruta=None):
    app = Flask(__name__)
    correlacion.instalar_registro()
    correlacion.instalar_en_flask(app, campos_ruta=campos_ruta)

    @app.route('/x')
    def x():
        return {'cid': correlacion.actual()}

    @app.route('/t/<id>')
    def t(id):
        logging.getLogger('prueba').warning('dentro de la peticion')
        return {'ok': True}

    return app


def test_flask_sin_cabecera_devuelve_un_uuid_nuevo():
    respuesta = _app().test_client().get('/x')
    assert respuesta.status_code == 200
    cid = respuesta.headers['X-Correlation-Id']
    assert UUID.match(cid)
    assert respuesta.get_json() == {'cid': cid}


def test_flask_respeta_la_cabecera_valida():
    respuesta = _app().test_client().get('/x', headers={'X-Correlation-Id': 'mi-id-de-prueba'})
    assert respuesta.headers['X-Correlation-Id'] == 'mi-id-de-prueba'
    assert respuesta.get_json() == {'cid': 'mi-id-de-prueba'}


def test_flask_reemplaza_la_cabecera_invalida():
    respuesta = _app().test_client().get('/x', headers={'X-Correlation-Id': 'con espacios y | raros'})
    cid = respuesta.headers['X-Correlation-Id']
    assert cid != 'con espacios y | raros'
    assert UUID.match(cid)


def test_flask_devuelve_la_cabecera_tambien_en_un_404():
    respuesta = _app().test_client().get('/no-existe')
    assert respuesta.status_code == 404
    assert UUID.match(respuesta.headers['X-Correlation-Id'])


def test_flask_restaura_el_contexto_tras_la_peticion():
    def caso():
        _app().test_client().get('/x', headers={'X-Correlation-Id': 'mi-id-de-prueba'})
        return correlacion.correlation_id_var.get(), correlacion.campos_actuales()

    assert en_contexto_limpio(caso) == (None, {})


def _linea_de_la_peticion(app, ruta):
    """Devuelve el registro `WARNING prueba` escrito durante la petición."""
    capturados = []

    class _Captura(logging.Handler):
        def emit(self, registro):
            capturados.append(registro)

    manejador = _Captura(level=logging.WARNING)
    logger = logging.getLogger('prueba')
    logger.addHandler(manejador)
    try:
        app.test_client().get(ruta, headers={'X-Correlation-Id': 'cid-ruta-1'})
    finally:
        logger.removeHandler(manejador)
    return capturados


def test_campos_ruta_escribe_el_id_de_la_ruta_en_el_registro():
    registros = _linea_de_la_peticion(_app(campos_ruta={'id': 'trabajo_id'}), '/t/abc-1')
    assert [r.campos for r in registros] == [' trabajo_id=abc-1']
    assert [r.correlation_id for r in registros] == ['cid-ruta-1']


def test_campos_ruta_descarta_un_valor_con_espacio():
    registros = _linea_de_la_peticion(_app(campos_ruta={'id': 'trabajo_id'}), '/t/con%20espacio')
    assert [r.campos for r in registros] == ['']


def test_campos_ruta_en_una_ruta_sin_ese_argumento_no_escribe_ninguno():
    app = _app(campos_ruta={'id': 'trabajo_id'})

    @app.route('/sin-id')
    def sin_id():
        logging.getLogger('prueba').warning('dentro de la peticion')
        return {'ok': True}

    registros = _linea_de_la_peticion(app, '/sin-id')
    assert [r.campos for r in registros] == ['']
