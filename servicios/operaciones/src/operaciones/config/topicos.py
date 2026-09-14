"""Nombres físicos de tópicos y suscripción — configuración, no código suelto.

Los valores por defecto son los que crea `infra/pulsar/inicializar.sh` /
`agregar-region.sh` (fuente de verdad: `infra/pulsar/topologia.env`).

A diferencia de Emparejamiento, Operaciones **no** despliega una réplica por
región: una sola suscripción durable (`operaciones`, Failover) se suscribe por
**patrón** a `evt-trabajo-.*`, así que una réplica nueva de Operaciones cubre
las regiones existentes y las que se agreguen en caliente (CA-8.4) sin
reconfigurar nada — es un consumidor de todas las regiones, no uno por región.
"""
import os

TENANT = os.getenv('PULSAR_TENANT', 'hogar-alpes')
NS_TRABAJOS = os.getenv('PULSAR_NS_TRABAJOS', 'trabajos')

SUSCRIPCION = 'operaciones'


def patron_evt_trabajo() -> str:
    return f'persistent://{TENANT}/{NS_TRABAJOS}/evt-trabajo-.*'
