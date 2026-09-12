"""Stream `cmd-acreditacion` — comandos hacia Acreditación.

Un solo stream para los tres comandos, discriminados por `tipo_comando`:

    SolicitarAcreditacion · AprobarAcreditacion · RevocarAcreditacion

Clave de partición: `proveedor_id`. El orden importa dentro de un mismo
proveedor —una aprobación no puede adelantar a su solicitud—, y por eso la
suscripción de Acreditación es Failover.

Por aquí entra la carga de 100.000 proveedores del escenario 8: la proyección de
Emparejamiento se llena por el mismo camino que en producción, no con un INSERT
directo contra su tabla.
"""
from pulsar.schema import Array, Long, Record, String

SOLICITAR = 'SolicitarAcreditacion'
APROBAR = 'AprobarAcreditacion'
REVOCAR = 'RevocarAcreditacion'


class ComandoAcreditacion(Record):
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
    tipo_comando = String(default=None, required_default=True)
    acreditacion_id = String(default=None, required_default=True)
    proveedor_id = String(default=None, required_default=True)
    pais = String(default=None, required_default=True)
    ciudad = String(default=None, required_default=True)
    # Oficios para los que se pide la acreditación (PLOMERIA, GAS, ...)
    categorias = Array(String(), default=None, required_default=True)
    nivel = String(default=None, required_default=True)
    vigencia_meses = Long(default=None, required_default=True)
    motivo = String(default=None, required_default=True)
