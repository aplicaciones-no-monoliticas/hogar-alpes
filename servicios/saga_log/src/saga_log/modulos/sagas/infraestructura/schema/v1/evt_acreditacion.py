"""Copia de solo lectura de `contratos/v1/evt_acreditacion.py` (CON-1).
`saga_log` observa los tres tipos de este stream y nunca publica en él
(ver `specs/002-saga-asignacion-trabajo/research.md` D9).
"""
from pulsar.schema import Array, Long, Record, String

TIPO_ACTUALIZADA = 'hogaralpes.acreditacion.actualizada.v1'
TIPO_VIGENCIA_CONFIRMADA = 'hogaralpes.acreditacion.vigencia-confirmada.v1'
TIPO_VIGENCIA_RECHAZADA = 'hogaralpes.acreditacion.vigencia-rechazada.v1'


class AcreditacionActualizada(Record):
    # --- sobre ---
    id = String(default=None, required_default=True)
    time = Long(default=None, required_default=True)
    ingestion = Long(default=None, required_default=True)
    specversion = String(default=None, required_default=True)
    type = String(default=None, required_default=True)
    datacontenttype = String(default=None, required_default=True)
    service_name = String(default=None, required_default=True)
    correlation_id = String(default=None, required_default=True)
    # --- carga: el estado completo del agregado ---
    acreditacion_id = String(default=None, required_default=True)
    proveedor_id = String(default=None, required_default=True)
    pais = String(default=None, required_default=True)
    ciudad = String(default=None, required_default=True)
    categorias = Array(String(), default=None, required_default=True)
    nivel = String(default=None, required_default=True)
    estado = String(default=None, required_default=True)
    vigente_hasta = String(default=None, required_default=True)
    version = Long(default=None, required_default=True)
    # --- saga (Entrega 5) ---
    trabajo_id = String(default=None, required_default=True)
    categoria = String(default=None, required_default=True)
