"""Nombres físicos de tópicos y suscripciones — configuración, no código suelto.

`saga_log` es puramente observador (D9 de
`specs/002-saga-asignacion-trabajo/research.md`): las tres suscripciones son
`Shared` y se pre-crean en `infra/pulsar/inicializar.sh` (T045). No hay ningún
tópico que este servicio publique.
"""
import os

TENANT = os.getenv('PULSAR_TENANT', 'hogar-alpes')
NS_TRABAJOS = os.getenv('PULSAR_NS_TRABAJOS', 'trabajos')
NS_ACREDITACION = os.getenv('PULSAR_NS_ACREDITACION', 'acreditacion')
NS_EMPAREJAMIENTO = os.getenv('PULSAR_NS_EMPAREJAMIENTO', 'emparejamiento')

SUSCRIPCION = 'saga-log'


def patron_evt_trabajo() -> str:
    """Por patrón, no por región (D6): una réplica cubre las regiones
    existentes y las que se agreguen en caliente, igual que ya hace GT para
    `cmd-trabajo-.*`."""
    return f'persistent://{TENANT}/{NS_TRABAJOS}/evt-trabajo-.*'


def topico_evt_emparejamiento() -> str:
    return f'persistent://{TENANT}/{NS_EMPAREJAMIENTO}/evt-emparejamiento'


def topico_evt_acreditacion() -> str:
    return f'persistent://{TENANT}/{NS_ACREDITACION}/evt-acreditacion'
