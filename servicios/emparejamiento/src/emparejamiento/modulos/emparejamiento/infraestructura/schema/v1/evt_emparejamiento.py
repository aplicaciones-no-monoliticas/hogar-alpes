"""Copia de `contratos/v1/evt_emparejamiento.py` (CON-1) — este servicio es el
único PRODUCTOR de este contrato.

Stream `evt-emparejamiento` — resultado del emparejamiento.

En la Entrega 4 **nadie lo consume**: se publica igual, porque es el paso 2 de
la transacción larga de referencia y lo escuchará la saga de la Entrega 5. La
guía del curso pide exactamente eso: que los servicios puedan oírse por tópicos
sin completar todavía la transacción.

Clave de partición: `trabajo_id`.
"""
from pulsar.schema import Array, Long, Record, String

TIPO_CANDIDATOS = 'hogaralpes.emparejamiento.candidatos-identificados.v1'
TIPO_SIN_CANDIDATOS = 'hogaralpes.emparejamiento.sin-candidatos.v1'
# Saga (Entrega 5, ver specs/002-saga-asignacion-trabajo/research.md D1/D2).
TIPO_PROVEEDOR_PROPUESTO = 'hogaralpes.emparejamiento.proveedor-propuesto.v1'
TIPO_CANDIDATOS_LIBERADOS = 'hogaralpes.emparejamiento.candidatos-liberados.v1'


class EventoEmparejamiento(Record):
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
    region = String(default=None, required_default=True)
    categoria = String(default=None, required_default=True)
    pais = String(default=None, required_default=True)
    ciudad = String(default=None, required_default=True)
    total_candidatos = Long(default=None, required_default=True)
    candidatos = Array(String(), default=None, required_default=True)
    # --- saga (Entrega 5) ---
    proveedor_id = String(default=None, required_default=True)
    motivo = String(default=None, required_default=True)
