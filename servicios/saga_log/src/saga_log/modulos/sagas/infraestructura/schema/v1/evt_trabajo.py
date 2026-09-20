"""Copia de solo lectura de `contratos/v1/evt_trabajo.py` (CON-1). `saga_log`
observa los cuatro pasos que pasan por este stream y nunca publica en él
(ver `specs/002-saga-asignacion-trabajo/research.md` D9).
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
    estado = String(default=None, required_default=True)
    estado_anterior = String(default=None, required_default=True)
