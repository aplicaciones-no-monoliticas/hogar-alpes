"""Servicios de atrás falsos pero reales: servidores HTTP en puertos efímeros.

Las pruebas ejercitan el camino completo (sockets, cabeceras, tiempos límite)
en lugar de simular `urlopen`. Los servidores escuchan en `127.0.0.1`, no en
`localhost`, para no depender de la resolución de nombres.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bff import crear_app

SERVICIOS = ('gestion-trabajos', 'operaciones', 'acreditacion', 'emparejamiento', 'saga-log')

VARIABLE_URL = {
    'gestion-trabajos': 'URL_TRABAJOS',
    'operaciones': 'URL_OPERACIONES',
    'acreditacion': 'URL_ACREDITACION',
    'emparejamiento': 'URL_EMPAREJAMIENTO',
    'saga-log': 'URL_SAGAS',
}

# En Windows, conectar a un puerto cerrado tarda ~2 s en fallar con "rechazada".
# Con un tiempo límite menor la prueba vería `TIMEOUT`; las que miden un tiempo
# límite lo bajan por su cuenta.
TIMEOUT_POR_DEFECTO_S = 3.0


class ServidorFalso:
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.recibidas = []
        self._respuestas = {}
        self._detenido = False
        servidor = self

        class Manejador(BaseHTTPRequestHandler):
            def _atender(self):
                ruta, _, consulta = self.path.partition('?')
                largo = int(self.headers.get('Content-Length') or 0)
                servidor.recibidas.append({
                    'metodo': self.command,
                    'ruta': ruta,
                    'consulta': consulta,
                    'cuerpo': self.rfile.read(largo) if largo else b'',
                    'cabeceras': {k.lower(): v for k, v in self.headers.items()},
                })
                respuesta = servidor._respuestas.get((self.command, ruta, consulta)) or servidor._respuestas.get((self.command, ruta, None)) or {
                    'codigo': 404,
                    'cuerpo': b'{"error": "no registrado en el servicio falso"}',
                    'tipo': 'application/json',
                    'demora_s': 0,
                    'cabeceras': {},
                }
                if respuesta['demora_s']:
                    time.sleep(respuesta['demora_s'])
                try:
                    self.send_response(respuesta['codigo'])
                    self.send_header('Content-Type', respuesta['tipo'])
                    self.send_header('Content-Length', str(len(respuesta['cuerpo'])))
                    for nombre, valor in respuesta['cabeceras'].items():
                        self.send_header(nombre, valor)
                    self.end_headers()
                    self.wfile.write(respuesta['cuerpo'])
                except (BrokenPipeError, ConnectionResetError):
                    pass  # el BFF ya se rindió por tiempo límite

            do_GET = do_POST = do_PUT = do_DELETE = _atender

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(('127.0.0.1', 0), Manejador)
        self._httpd.daemon_threads = True
        self.url = f'http://127.0.0.1:{self._httpd.server_port}'
        # El intervalo por defecto (0.5 s) haría que cada `detener()` tardara medio segundo.
        threading.Thread(target=self._httpd.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()

    def responder(self, metodo, ruta, codigo=200, cuerpo=b'', tipo='application/json', demora_s=0, cabeceras=None, consulta=None):
        if not isinstance(cuerpo, bytes):
            cuerpo = json.dumps(cuerpo).encode()
        self._respuestas[(metodo, ruta, consulta)] = {
            'codigo': codigo,
            'cuerpo': cuerpo,
            'tipo': tipo,
            'demora_s': demora_s,
            'cabeceras': cabeceras or {},
        }

    def detener(self):
        """Cierra el socket: a partir de aquí, las conexiones son rechazadas."""
        if not self._detenido:
            self._detenido = True
            self._httpd.shutdown()
            self._httpd.server_close()


@pytest.fixture
def atras():
    servidores = {nombre: ServidorFalso(nombre) for nombre in SERVICIOS}
    yield servidores
    for servidor in servidores.values():
        servidor.detener()


@pytest.fixture
def hacer_app(atras):
    """Fábrica de apps contra los servidores falsos; `**cambios` pisa cualquier variable."""

    def fabrica(**cambios):
        configuracion = {
            'TESTING': True,
            'TIMEOUT_REENVIO_S': TIMEOUT_POR_DEFECTO_S,
            'TIMEOUT_COMPUESTO_S': TIMEOUT_POR_DEFECTO_S,
            **{VARIABLE_URL[nombre]: servidor.url for nombre, servidor in atras.items()},
        }
        configuracion.update(cambios)
        return crear_app(configuracion)

    return fabrica


@pytest.fixture
def app(hacer_app):
    return hacer_app()


@pytest.fixture
def cliente(app):
    return app.test_client()
