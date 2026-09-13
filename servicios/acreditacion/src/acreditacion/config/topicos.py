"""Nombres físicos de tópicos y suscripciones — configuración, no código suelto.

Los valores por defecto son los que crea `infra/pulsar/inicializar.sh` (fuente
de verdad: `infra/pulsar/topologia.env`). Se pueden sobrescribir por variable de
entorno para apuntar a otro tenant/namespace sin tocar código, igual que hace
`infra/pulsar/comun.sh` del lado de la infraestructura.
"""
import os

TENANT = os.getenv('PULSAR_TENANT', 'hogar-alpes')
NS_ACREDITACION = os.getenv('PULSAR_NS_ACREDITACION', 'acreditacion')

SUSCRIPCION_COMANDOS = 'acreditacion'


def topico_cmd_acreditacion() -> str:
    return f'persistent://{TENANT}/{NS_ACREDITACION}/cmd-acreditacion'


def topico_evt_acreditacion() -> str:
    return f'persistent://{TENANT}/{NS_ACREDITACION}/evt-acreditacion'
