"""Stream `evt-trabajo-{región}` — eventos de integración de Gestión de Trabajos.

Lo consumen Operaciones (escenario 6) y Emparejamiento (escenario 8), cada uno
con su propia suscripción y su propio cursor.

**Un solo stream para los dos tipos de evento**, discriminados por `type`:

    hogaralpes.trabajo.creado.v1
    hogaralpes.trabajo.estado-cambiado.v1

Es la corrección de la brecha `G-2`. Con un tópico por tipo de evento no hay
orden entre ellos: tras una caída, Operaciones podía recibir el cambio de estado
antes que la creación del trabajo y lo descartaba en silencio. Con un stream
único y `trabajo_id` como clave, el orden dentro de un mismo trabajo está
garantizado.

Tipo de evento: **integración (delta)**. Comunica hechos que disparan
comportamiento —abrir un seguimiento, emparejar— y debe ser pequeño, porque el
escenario 6 obliga a retener el backlog mientras el consumidor está caído.
`estado_anterior` viene vacío en la creación.
"""
from pulsar.schema import Long, Record, String

TIPO_CREADO = 'hogaralpes.trabajo.creado.v1'
TIPO_ESTADO_CAMBIADO = 'hogaralpes.trabajo.estado-cambiado.v1'


class EventoTrabajo(Record):
    # --- sobre ---
    id = String(default=None, required_default=True)
    time = Long(default=None, required_default=True)
    ingestion = Long(default=None, required_default=True)
    specversion = String(default=None, required_default=True)
    type = String(default=None, required_default=True)
    datacontenttype = String(default=None, required_default=True)
    service_name = String(default=None, required_default=True)
    correlation_id = String(default=None, required_default=True)
    # --- carga ---
    trabajo_id = String(default=None, required_default=True)
    partner_id = String(default=None, required_default=True)
    canal = String(default=None, required_default=True)
    pais = String(default=None, required_default=True)
    ciudad = String(default=None, required_default=True)
    categoria = String(default=None, required_default=True)
    urgencia = String(default=None, required_default=True)
    # Texto, no enumeración Avro: una enumeración cerrada rompería MOD-3, que
    # exige agregar un estado nuevo sin tocar a los consumidores.
    estado = String(default=None, required_default=True)
    estado_anterior = String(default=None, required_default=True)
