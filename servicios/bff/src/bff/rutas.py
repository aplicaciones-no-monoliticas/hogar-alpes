"""Tabla de reenvío: las rutas de los servicios de atrás, como datos.

Es una lista explícita y no un comodín para que un `404` de un servicio (el
recurso no existe) se distinga del `404` propio del BFF (la ruta no existe).
"""
import re
from typing import NamedTuple

from .config import GRUPO_DE


class Regla(NamedTuple):
    metodo: str
    patron: str
    servicio: str
    # Las rutas que inician una saga devuelven además el identificador en el cuerpo.
    agrega_correlacion: bool = False
    # Campo de registro que lleva el `<id>` de la ruta (o el `id` que devuelve la creación).
    campo_id: str | None = None


RUTAS = [
    Regla('POST', '/trabajos', 'gestion-trabajos', agrega_correlacion=True, campo_id='trabajo_id'),
    Regla('GET', '/trabajos/<id>', 'gestion-trabajos', campo_id='trabajo_id'),
    Regla('GET', '/trabajos', 'gestion-trabajos'),
    Regla('PUT', '/trabajos/<id>/estado', 'gestion-trabajos', campo_id='trabajo_id'),
    Regla('GET', '/seguimientos/<id>', 'operaciones', campo_id='trabajo_id'),
    Regla('GET', '/seguimientos/conteo', 'operaciones'),
    Regla('GET', '/eventos-procesados/conteo', 'operaciones'),
    Regla('POST', '/acreditaciones', 'acreditacion'),
    Regla('PUT', '/acreditaciones/<id>/aprobar', 'acreditacion'),
    Regla('PUT', '/acreditaciones/<id>/revocar', 'acreditacion'),
    Regla('GET', '/acreditaciones/<id>', 'acreditacion'),
    Regla('GET', '/acreditaciones/<id>/eventos', 'acreditacion'),
    Regla('GET', '/candidatos', 'emparejamiento'),
    Regla('GET', '/emparejamientos/<id>', 'emparejamiento', campo_id='trabajo_id'),
    Regla('GET', '/sagas/<id>', 'saga-log', campo_id='trabajo_id'),
    Regla('GET', '/sagas', 'saga-log'),
    Regla('GET', '/sagas/resumen', 'saga-log'),
]


def _notacion(regla: Regla) -> str:
    return f"{regla.metodo} {re.sub(r'<[^>]+>', '{id}', regla.patron)}"


def _agrupar() -> dict:
    grupos = {}
    for regla in RUTAS:
        grupos.setdefault(GRUPO_DE[regla.servicio], []).append(_notacion(regla))
    return grupos


GRUPOS = _agrupar()
GRUPOS['Compuestos'] = [
    'GET /trabajos/{id}/completo',
    'GET /proveedores/{id}/completo',
    'GET /estado-del-sistema',
    'POST /trabajos/asignacion',
]
