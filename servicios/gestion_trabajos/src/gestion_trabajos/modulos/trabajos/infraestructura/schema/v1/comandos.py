"""Copia de `contratos/v1/cmd_trabajo.py` (CON-1) — Gestión de Trabajos es el
único CONSUMIDOR de este contrato (lo publica el generador de carga, y en la
Entrega 5 el Gateway de Partners).

**Reemplaza al `ComandoCrearTrabajo(ComandoIntegracion)` anterior**, que
anidaba la carga bajo un solo campo `data` y no declaraba `default` en ningún
campo — el mismo defecto que encontró CON-1 en los eventos (el sobre nunca
viajaba, y sin `default` el broker rechaza cualquier evolución). Este contrato
sigue la regla de INF-0: todo campo `Tipo(default=None, required_default=True)`.

`trabajo_id` es la evolución compatible que demuestra CA-E1 (GT-4): lo genera
el productor, no el servicio. Da la clave de partición desde el primer
mensaje del flujo y hace la creación **idempotente** ante reintentos del
productor — dos comandos con el mismo `trabajo_id` crean un único trabajo
(`CrearTrabajoHandler`, §4.1 de la especificación).
"""
from pulsar.schema import Long, Record, String

TIPO_CREAR = 'hogaralpes.trabajo.crear.v1'


class ComandoCrearTrabajo(Record):
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
    canal = String(default=None, required_default=True)
    partner_id = String(default=None, required_default=True)
    referencia_externa = String(default=None, required_default=True)
    categoria = String(default=None, required_default=True)
    urgencia = String(default=None, required_default=True)
    pais = String(default=None, required_default=True)
    ciudad = String(default=None, required_default=True)
    direccion = String(default=None, required_default=True)
    descripcion = String(default=None, required_default=True)
