"""Identificador de correlación: información de transporte, nunca de negocio.

Entra por el borde (cabecera HTTP o mensaje consumido), vive en un `ContextVar`
y sale por el borde (mensaje publicado, línea de registro). Este archivo es
idéntico en todos los servicios; no importa dominio ni nombra ninguno.
"""
import contextlib
import logging
import re
import uuid
from contextvars import ContextVar

CABECERA = 'X-Correlation-Id'

# Constante y no variable de entorno: así el archivo sigue idéntico en cada copia.
PATRON = re.compile(r'[A-Za-z0-9._:-]{1,64}')
_PATRON_CAMPO = re.compile(r'[a-z][a-z0-9_]{0,31}')

correlation_id_var = ContextVar('correlation_id', default=None)
_campos_var = ContextVar('campos_registro', default=None)

_registro_instalado = False


def normalizar(valor) -> str | None:
    """Devuelve `valor` si tiene la forma válida; si no, `None` (se trata como ausente)."""
    if isinstance(valor, str) and PATRON.fullmatch(valor):
        return valor
    return None


def actual() -> str:
    """Identificador vigente; si no hay, crea uno y lo deja fijado para que sobre y propiedades coincidan."""
    valor = correlation_id_var.get()
    if valor is None:
        valor = str(uuid.uuid4())
        correlation_id_var.set(valor)
    return valor


def _fijar(valor):
    return correlation_id_var.set(valor), _campos_var.set({})


def _restaurar(tokens):
    token_id, token_campos = tokens
    _campos_var.reset(token_campos)
    correlation_id_var.reset(token_id)


@contextlib.contextmanager
def contexto(valor):
    """Fija `valor` (o uno nuevo si no es válido) durante el bloque y restaura el anterior al salir."""
    nuevo = normalizar(valor) or str(uuid.uuid4())
    tokens = _fijar(nuevo)
    try:
        yield nuevo
    finally:
        _restaurar(tokens)


def desde_mensaje(valor, mensaje) -> str | None:
    """Identificador de un mensaje consumido: campo del sobre, luego propiedad; `None` si ninguno es válido."""
    del_sobre = normalizar(getattr(valor, 'correlation_id', None))
    if del_sobre:
        return del_sobre
    return normalizar((mensaje.properties() or {}).get('correlation_id'))


def agregar_campos(**campos) -> None:
    """Suma campos a las líneas de registro del contexto activo; descarta lo que no cumpla la forma."""
    actuales = _campos_var.get()
    if actuales is None:
        return
    validos = {
        nombre: valor
        for nombre, valor in campos.items()
        if _PATRON_CAMPO.fullmatch(nombre) and normalizar(valor)
    }
    # Copia y no mutación: un hilo hijo con `copy_context()` comparte el diccionario.
    _campos_var.set({**actuales, **validos})


def campos_actuales() -> dict:
    return dict(_campos_var.get() or {})


def instalar_registro() -> None:
    """Agrega `correlation_id` y `campos` a todo registro del proceso (`-` y vacío fuera de contexto)."""
    global _registro_instalado
    if _registro_instalado:
        return
    fabrica_anterior = logging.getLogRecordFactory()

    def fabrica(*args, **kwargs):
        registro = fabrica_anterior(*args, **kwargs)
        registro.correlation_id = correlation_id_var.get() or '-'
        registro.campos = ''.join(f' {k}={v}' for k, v in (_campos_var.get() or {}).items())
        return registro

    logging.setLogRecordFactory(fabrica)
    _registro_instalado = True


def instalar_en_flask(app, campos_ruta=None) -> None:
    """Ganchos HTTP: fija el contexto al entrar, devuelve la cabecera y restaura al salir.

    `campos_ruta` = `{argumento_de_ruta: nombre_de_campo}`: copia esos argumentos a los campos de registro.
    """
    from flask import g, request

    @app.before_request
    def _entrada():
        g._correlacion_tokens = _fijar(normalizar(request.headers.get(CABECERA)) or str(uuid.uuid4()))
        argumentos = request.view_args or {}
        for argumento, campo in (campos_ruta or {}).items():
            if argumento in argumentos:
                agregar_campos(**{campo: argumentos[argumento]})

    @app.after_request
    def _salida(respuesta):
        respuesta.headers[CABECERA] = actual()
        return respuesta

    @app.teardown_request
    def _limpieza(_excepcion):
        tokens = g.pop('_correlacion_tokens', None)
        if tokens is not None:
            _restaurar(tokens)
