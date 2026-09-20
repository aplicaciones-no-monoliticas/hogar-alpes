"""Errores propios del BFF: siempre JSON, con `correlation_id`, sin trazas.

Nunca se copia a la respuesta el texto de un servicio ni una excepción.
"""
import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException

from . import correlacion, rutas

logger = logging.getLogger(__name__)


def _respuesta(codigo: int, cuerpo: dict):
    respuesta = jsonify({**cuerpo, 'correlation_id': correlacion.actual()})
    respuesta.status_code = codigo
    return respuesta


def servicio_no_disponible(servicio: str, motivo: str):
    return _respuesta(503, {
        'error': f'Servicio no disponible: {servicio}',
        'servicio': servicio,
        'motivo': motivo,
    })


def servicios_no_disponibles(nombres: list):
    return _respuesta(503, {
        'error': 'Servicios no disponibles: ' + ', '.join(nombres),
        'servicio': list(nombres),
    })


def error_upstream(servicio: str, status: int):
    return _respuesta(502, {
        'error': f'El servicio {servicio} respondió con un error interno',
        'servicio': servicio,
        'status_upstream': status,
    })


def _ruta_no_encontrada(_error):
    return _respuesta(404, {
        'error': 'Ruta no encontrada',
        'grupos_disponibles': [{'grupo': grupo, 'rutas': lista} for grupo, lista in rutas.GRUPOS.items()],
    })


def _metodo_no_permitido(error):
    return _respuesta(405, {
        'error': 'Método no permitido',
        'metodos_permitidos': sorted(error.valid_methods or []),
    })


def _error_no_previsto(error):
    if isinstance(error, HTTPException):
        return _respuesta(error.code, {'error': error.name})
    logger.exception('Error no previsto en el BFF')
    return _respuesta(500, {'error': 'Error interno del BFF'})


def registrar(app) -> None:
    app.register_error_handler(404, _ruta_no_encontrada)
    app.register_error_handler(405, _metodo_no_permitido)
    app.register_error_handler(Exception, _error_no_previsto)
