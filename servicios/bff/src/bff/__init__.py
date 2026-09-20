"""BFF de Hogar de los Alpes: un solo punto de entrada hacia los servicios.

Componente de borde: no tiene base de datos, no habla con el broker y no guarda
estado entre peticiones. Reenvía, compone y pone el identificador de correlación.
"""
import logging
import os
import time
import urllib.parse

from flask import Flask, g, request

from . import compuestos, config, correlacion, errores, reenvio, rutas, salud

FORMATO_REGISTRO = '%(levelname)s %(name)s | cid=%(correlation_id)s%(campos)s | %(message)s'

peticiones = logging.getLogger('bff.peticion')


def _instalar_registro_por_peticion(app: Flask) -> None:
    """Una línea por petición: método, ruta, servicio destino, código y milisegundos."""

    @app.before_request
    def _inicio():
        g.inicio = time.perf_counter()

    @app.after_request
    def _linea(respuesta):
        milisegundos = round((time.perf_counter() - g.get('inicio', time.perf_counter())) * 1000)
        # La ruta ya viene decodificada: se recodifica para que un `%0A` no parta la línea de registro.
        ruta = urllib.parse.quote(request.path, safe='/:')
        peticiones.info(
            '%s %s -> %s %s %sms',
            request.method, ruta, g.get('servicio_destino', '-'), respuesta.status_code, milisegundos,
        )
        return respuesta


def crear_app(configuracion: dict | None = None) -> Flask:
    correlacion.instalar_registro()
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format=FORMATO_REGISTRO)

    app = Flask(__name__)
    app.json.sort_keys = False
    app.config['BFF'] = config.cargar(configuracion)
    app.config['TESTING'] = (configuracion or {}).get('TESTING', False)

    # Antes que todo lo demás: así cada respuesta, incluidas las de error, lleva la cabecera.
    correlacion.instalar_en_flask(app)
    _instalar_registro_por_peticion(app)

    app.register_blueprint(salud.bp)
    app.register_blueprint(compuestos.compuestos_bp)
    for i, regla in enumerate(rutas.RUTAS):
        app.add_url_rule(
            regla.patron,
            endpoint=f'reenvio_{i}',
            view_func=reenvio.crear_vista(regla),
            methods=[regla.metodo],
        )
    errores.registrar(app)
    return app
