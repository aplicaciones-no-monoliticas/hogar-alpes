"""El BFF no tiene base de datos, ni broker, ni estado (CA-2.3, FR-007, FR-008, FR-009)."""
import json
import re
from pathlib import Path

SERVICIO = Path(__file__).resolve().parents[1]
OPERACIONES = SERVICIO.parent / 'operaciones'

PROHIBIDAS = ('pulsar', 'sqlalchemy', 'psycopg2', 'fastavro', 'pydispatcher')


def _lineas(archivo: Path) -> list:
    return [linea.strip() for linea in archivo.read_text(encoding='utf-8').splitlines() if linea.strip()]


def test_requirements_no_trae_dependencias_de_base_de_datos_ni_de_broker():
    texto = (SERVICIO / 'requirements.txt').read_text(encoding='utf-8').lower()
    for prohibida in PROHIBIDAS:
        assert prohibida not in texto, prohibida


def test_requirements_son_exactamente_flask_gunicorn_y_pytest():
    assert _lineas(SERVICIO / 'requirements.txt') == ['Flask==3.0.3', 'gunicorn==22.0.0', 'pytest==8.2.0']


def test_los_pines_son_los_mismos_que_usa_operaciones():
    de_operaciones = set(_lineas(OPERACIONES / 'requirements.txt'))
    assert {'Flask==3.0.3', 'gunicorn==22.0.0', 'pytest==8.2.0'} <= de_operaciones


def test_el_dockerfile_no_compila_nada_ni_instala_paquetes_del_sistema():
    dockerfile = (SERVICIO / 'Dockerfile').read_text(encoding='utf-8').lower()
    for prohibida in ('gcc', 'libpq', 'apt-get'):
        assert prohibida not in dockerfile, prohibida


def test_ningun_modulo_importa_pulsar_sqlalchemy_ni_psycopg2():
    importa = re.compile(r'^\s*(?:import|from)\s+(pulsar|sqlalchemy|psycopg2)\b', re.MULTILINE)
    for archivo in (SERVICIO / 'src').rglob('*.py'):
        assert importa.search(archivo.read_text(encoding='utf-8')) is None, archivo.name


def test_dos_instancias_contestan_igual_sin_coordinarse(hacer_app, atras):
    atras['gestion-trabajos'].responder('GET', '/trabajos/abc', 200, b'{"id": "abc", "estado": "CREADO"}')
    atras['emparejamiento'].responder('GET', '/emparejamientos/abc', 404, b'{"error": "sin emparejamiento"}')
    primera, segunda = hacer_app().test_client(), hacer_app().test_client()

    respuestas = []
    for cliente in (primera, segunda, primera, segunda):
        for ruta in ('/trabajos/abc', '/emparejamientos/abc', '/health'):
            r = cliente.get(ruta)
            respuestas.append((ruta, r.status_code, r.data))

    esperado = {
        '/trabajos/abc': (200, b'{"id": "abc", "estado": "CREADO"}'),
        '/emparejamientos/abc': (404, b'{"error": "sin emparejamiento"}'),
    }
    for ruta, codigo, cuerpo in respuestas:
        if ruta in esperado:
            assert (codigo, cuerpo) == esperado[ruta]
        else:
            assert codigo == 200
            assert json.loads(cuerpo) == {'status': 'up', 'service': 'bff'}
    assert len(respuestas) == 12
