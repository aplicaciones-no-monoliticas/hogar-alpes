"""Nombres físicos de tópicos y suscripciones — configuración, no código suelto.

Los valores por defecto son los que crea `infra/pulsar/inicializar.sh` /
`agregar-region.sh` (fuente de verdad: `infra/pulsar/topologia.env`). Cada
réplica de Emparejamiento atiende **una** región, dada por `REGION`: es la
misma unidad de despliegue por región que describe el plan técnico §3.2 —
agregar una región es agregar una réplica nueva, no tocar las que ya corren.
"""
import os

TENANT = os.getenv('PULSAR_TENANT', 'hogar-alpes')
NS_TRABAJOS = os.getenv('PULSAR_NS_TRABAJOS', 'trabajos')
NS_ACREDITACION = os.getenv('PULSAR_NS_ACREDITACION', 'acreditacion')
NS_EMPAREJAMIENTO = os.getenv('PULSAR_NS_EMPAREJAMIENTO', 'emparejamiento')

SUSCRIPCION_PROYECCION = 'emparejamiento-proyeccion'
# Saga (Entrega 5, D6 de specs/002-saga-asignacion-trabajo/research.md).
SUSCRIPCION_SAGA = 'emparejamiento-saga'


def region() -> str:
    r = os.getenv('REGION', '')
    if not r:
        raise RuntimeError(
            'REGION no está configurada: cada réplica de emparejamiento atiende una sola región'
        )
    return r


def topico_evt_trabajo(region_: str | None = None) -> str:
    return f'persistent://{TENANT}/{NS_TRABAJOS}/evt-trabajo-{region_ or region()}'


def suscripcion_regional(region_: str | None = None) -> str:
    return f'emparejamiento-{region_ or region()}'


def topico_evt_acreditacion() -> str:
    return f'persistent://{TENANT}/{NS_ACREDITACION}/evt-acreditacion'


def topico_evt_emparejamiento() -> str:
    return f'persistent://{TENANT}/{NS_EMPAREJAMIENTO}/evt-emparejamiento'
