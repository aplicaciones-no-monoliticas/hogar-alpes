"""Direcciones de los servicios de atrás y tiempos límite.

Se leen del entorno en cada llamada a `cargar` (no al importar), y `overrides`
permite fijarlos en las pruebas con las mismas claves que las variables.
"""
import os
from dataclasses import dataclass
from typing import NamedTuple


class Servicio(NamedTuple):
    nombre: str
    grupo: str
    url_base: str


# (nombre, grupo, variable de entorno, valor por defecto en Compose)
_SERVICIOS = (
    ('gestion-trabajos', 'Trabajos', 'URL_TRABAJOS', 'http://gestion-trabajos:5000'),
    ('operaciones', 'Seguimiento', 'URL_OPERACIONES', 'http://operaciones:5000'),
    ('acreditacion', 'Acreditaciones', 'URL_ACREDITACION', 'http://acreditacion:5000'),
    ('emparejamiento', 'Emparejamiento', 'URL_EMPAREJAMIENTO', 'http://emparejamiento:5000'),
    ('saga-log', 'Sagas', 'URL_SAGAS', 'http://saga-log:5000'),
)

GRUPO_DE = {nombre: grupo for nombre, grupo, _, _ in _SERVICIOS}


@dataclass(frozen=True)
class Configuracion:
    servicios: dict
    timeout_reenvio_s: float
    timeout_compuesto_s: float


def cargar(overrides: dict | None = None) -> Configuracion:
    overrides = overrides or {}

    def leer(clave, defecto):
        return overrides.get(clave, os.getenv(clave, defecto))

    servicios = {
        nombre: Servicio(nombre, grupo, str(leer(variable, defecto)).rstrip('/'))
        for nombre, grupo, variable, defecto in _SERVICIOS
    }
    return Configuracion(
        servicios=servicios,
        timeout_reenvio_s=float(leer('TIMEOUT_REENVIO_S', '5')),
        timeout_compuesto_s=float(leer('TIMEOUT_COMPUESTO_S', '1.5')),
    )
