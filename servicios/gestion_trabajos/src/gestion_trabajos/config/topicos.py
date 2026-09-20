"""Nombres físicos de tópicos y suscripciones — configuración, no código suelto.

Los valores por defecto son los que crea `infra/pulsar/inicializar.sh` (fuente
de verdad: `infra/pulsar/topologia.env`). Se pueden sobrescribir por variable de
entorno para apuntar a otro tenant o namespace sin tocar código.

**Gestión de Trabajos es el único PRODUCTOR de `evt-trabajo`.** Publica en el
stream de la región del trabajo, con `trabajo_id` como clave de partición: el
orden dentro de un mismo trabajo queda garantizado aunque el tópico esté
particionado (escenario 8), y los dos tipos de evento viajan por el mismo stream
para que no se adelante un cambio de estado a la creación (brecha `G-2`).

El mapeo país → región es **configuración**: abrir un país es agregar una
entrada aquí o pasar `REGIONES_EXTRA`, no modificar el dominio. Es la misma
lógica que el sidecar regional del escenario 2.
"""
import json
import os

TENANT = os.getenv('PULSAR_TENANT', 'hogar-alpes')
NS_TRABAJOS = os.getenv('PULSAR_NS_TRABAJOS', 'trabajos')
NS_ACREDITACION = os.getenv('PULSAR_NS_ACREDITACION', 'acreditacion')
NS_EMPAREJAMIENTO = os.getenv('PULSAR_NS_EMPAREJAMIENTO', 'emparejamiento')

# Debe coincidir con la suscripción que `inicializar.sh` pre-crea sobre
# `cmd-trabajo-{región}`. Si no coincide, la suscripción pre-creada queda
# huérfana y los comandos publicados antes de que el servicio arranque no se
# retienen para nadie.
SUSCRIPCION_COMANDOS = 'gestion-trabajos'
# Saga (Entrega 5, D6 de specs/002-saga-asignacion-trabajo/research.md).
SUSCRIPCION_SAGA = 'gestion-trabajos-saga'

REGIONES = {'CO': 'andina', 'MX': 'norteamerica', 'BR': 'conosur', 'AR': 'conosur'}
REGION_POR_DEFECTO = os.getenv('REGION_POR_DEFECTO', 'andina')

# Permite agregar países sin redesplegar la imagen: REGIONES_EXTRA='{"PE":"andina"}'
REGIONES.update(json.loads(os.getenv('REGIONES_EXTRA', '{}')))


def region(pais: str | None) -> str:
    return REGIONES.get((pais or '').upper(), REGION_POR_DEFECTO)


def topico_evt_trabajo(pais: str | None = None, region_: str | None = None) -> str:
    return f'persistent://{TENANT}/{NS_TRABAJOS}/evt-trabajo-{region_ or region(pais)}'


def patron_cmd_trabajo() -> str:
    """Por patrón, no por región: una réplica cubre las regiones existentes y las
    que se agreguen en caliente (CA-8.4) sin reconfigurar nada."""
    return f'persistent://{TENANT}/{NS_TRABAJOS}/cmd-trabajo-.*'


def topico_evt_emparejamiento() -> str:
    return f'persistent://{TENANT}/{NS_EMPAREJAMIENTO}/evt-emparejamiento'


def topico_evt_acreditacion() -> str:
    return f'persistent://{TENANT}/{NS_ACREDITACION}/evt-acreditacion'
