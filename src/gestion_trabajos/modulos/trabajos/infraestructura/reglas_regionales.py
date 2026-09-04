"""ADAPTADOR del sidecar de reglas regionales (escenario 2).

Hoy lee un archivo de configuración montado como volumen; mañana puede hablar
HTTP con un sidecar desplegado aparte. Ni el dominio ni los handlers cambian:
solo se sustituye esta clase.

Incorporar Perú = agregar una entrada a `reglas_regionales.json` y reiniciar el
sidecar. Cero archivos del servicio base modificados.
"""
import json
import os
from functools import lru_cache

from ..dominio.servicios import ServicioReglasRegionales

RUTA_DEFECTO = os.getenv(
    'RUTA_REGLAS_REGIONALES',
    os.path.join(os.path.dirname(__file__), 'reglas_regionales.json'),
)


@lru_cache(maxsize=1)
def _cargar(ruta: str) -> dict:
    with open(ruta, encoding='utf-8') as f:
        return json.load(f)


class SidecarReglasRegionales(ServicioReglasRegionales):
    def __init__(self, ruta: str = RUTA_DEFECTO):
        self.ruta = ruta

    def _region(self, pais: str) -> dict:
        reglas = _cargar(self.ruta)
        return reglas.get(pais.upper(), reglas.get('_default', {}))

    def categorias_permitidas(self, pais: str) -> list[str]:
        return self._region(pais).get('categorias', [])

    def urgencias_permitidas(self, pais: str) -> list[str]:
        return self._region(pais).get('urgencias', [])
