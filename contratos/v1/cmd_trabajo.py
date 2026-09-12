"""Stream `cmd-trabajo-{región}` — comandos hacia Gestión de Trabajos.

Lo publica el generador de carga (y el Gateway de Partners en la Entrega 5).
Clave de partición: `trabajo_id`.

`trabajo_id` lo genera el **productor**, no el servicio. Dos consecuencias:

1. Hay clave de partición desde el primer mensaje del flujo.
2. La creación es idempotente: si el productor reintenta, no se crean dos
   trabajos.

Es además el campo con el que se demuestra CA-E1, la evolución compatible del
esquema.

Los ocho primeros campos son el sobre común: se repiten a propósito, porque la
herencia de `Record` pierde los campos del padre (ver `mensajes.py`).
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
