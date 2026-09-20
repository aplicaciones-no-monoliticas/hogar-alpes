"""Cliente HTTP hacia los servicios de atrás, con la biblioteca estándar.

Devuelve la respuesta de negocio (`< 500`, incluidas las `3xx`) sin tocarla y
convierte todo lo demás en `FalloAtras` con un motivo clasificado.
"""
import http.client
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple

from . import correlacion

_CABECERAS_DE_SALTO = {'connection', 'transfer-encoding', 'keep-alive'}
_FUERA_DE_ASCII_IMPRIMIBLE = re.compile(rb'[^\x21-\x7e]')


class Respuesta(NamedTuple):
    codigo: int
    cuerpo: bytes
    tipo_contenido: str | None
    location: str | None


class FalloAtras(Exception):
    """`motivo` ∈ TIMEOUT · CONEXION_RECHAZADA · DNS · ERROR_INTERNO_UPSTREAM."""

    def __init__(self, servicio: str, motivo: str, status: int | None = None):
        super().__init__(f'{servicio}: {motivo}')
        self.servicio = servicio
        self.motivo = motivo
        self.status = status


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        # Con `None` la `3xx` llega tal cual como `HTTPError` y el BFF no la sigue.
        return None


# `ProxyHandler({})`: las llamadas hacia adentro nunca deben salir por un proxy del entorno.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SinRedireccion())


def _ruta_codificada(ruta: str) -> str:
    # Werkzeug ya decodificó la ruta: se codifica cada segmento para que `%3F`, `%23`,
    # espacios o saltos de línea no alteren la consulta ni la URL hacia atrás.
    return '/'.join(urllib.parse.quote(segmento, safe='') for segmento in ruta.split('/'))


def _consulta_segura(consulta: bytes) -> str:
    # Va cruda; solo se codifica lo que nunca podría viajar en una línea de petición.
    return _FUERA_DE_ASCII_IMPRIMIBLE.sub(lambda m: b'%%%02X' % m.group()[0], consulta).decode('ascii')


def _resolver(url_base: str, limite_s: float) -> None:
    """`getaddrinfo` no admite tiempo límite (con un nombre que no existe puede tardar
    segundos): se acota con un hilo propio por llamada, sin compartir un grupo que un
    servicio caído pudiera saturar."""
    partes = urllib.parse.urlsplit(url_base)
    resultado = {}

    def buscar():
        try:
            socket.getaddrinfo(partes.hostname, partes.port or 80)
        except OSError as error:
            resultado['error'] = error

    hilo = threading.Thread(target=buscar, daemon=True)
    hilo.start()
    hilo.join(limite_s)
    if hilo.is_alive():
        raise TimeoutError('la resolución del nombre no terminó a tiempo')
    if 'error' in resultado:
        raise resultado['error']


def _clasificar(excepcion: BaseException) -> str:
    causa = excepcion.reason if isinstance(excepcion, urllib.error.URLError) else excepcion
    if isinstance(causa, TimeoutError):
        return 'TIMEOUT'
    if isinstance(causa, socket.gaierror):
        return 'DNS'
    return 'CONEXION_RECHAZADA'


def _leer(respuesta) -> Respuesta:
    return Respuesta(
        codigo=respuesta.status,
        cuerpo=respuesta.read(),
        tipo_contenido=respuesta.headers.get('Content-Type'),
        location=respuesta.headers.get('Location'),
    )


def llamar(servicio, metodo, ruta, consulta=b'', cuerpo=None, cabeceras=None, timeout=5.0) -> Respuesta:
    """`servicio` es un `config.Servicio`; `ruta` viene decodificada; `consulta` va cruda."""
    consulta = _consulta_segura(consulta)
    url = servicio.url_base + _ruta_codificada(ruta) + ('?' + consulta if consulta else '')
    peticion = urllib.request.Request(url, data=cuerpo, method=metodo)
    for nombre, valor in (cabeceras or {}).items():
        if valor and nombre.lower() not in _CABECERAS_DE_SALTO:
            peticion.add_header(nombre, valor)
    peticion.add_header(correlacion.CABECERA, correlacion.actual())

    try:
        _resolver(servicio.url_base, timeout)
        with _opener.open(peticion, timeout=timeout) as respuesta:
            return _leer(respuesta)
    except urllib.error.HTTPError as error:
        with error:
            if error.code >= 500:
                raise FalloAtras(servicio.nombre, 'ERROR_INTERNO_UPSTREAM', status=error.code) from None
            return _leer(error)
    except (OSError, http.client.HTTPException) as error:
        raise FalloAtras(servicio.nombre, _clasificar(error)) from None
