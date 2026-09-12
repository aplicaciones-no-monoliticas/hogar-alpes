"""Stream `evt-acreditacion` — eventos de **carga de estado** de Acreditación.

Lo consume la proyección de proveedores de Emparejamiento (escenario 8).

A diferencia de `evt-trabajo`, cada mensaje lleva el **estado completo** de la
acreditación, no solo lo que cambió. Tres razones, todas del escenario 8:

1. La proyección debe responder consultas **sin preguntarle nada** a
   Acreditación: no hay llamadas síncronas entre servicios.
2. El `upsert` es idempotente y tolerante al desorden: se aplica solo si
   `version` es mayor que la almacenada.
3. **Converge.** Si un evento se pierde o llega tarde, el siguiente corrige la
   proyección. Con eventos delta, una pérdida la dejaría divergente para
   siempre, y eso es justo el riesgo `PS-10`: publicarle trabajos a un proveedor
   cuya acreditación acaba de vencer.

El costo aceptado es el tamaño del mensaje. Se paga porque el volumen de
acreditaciones es bajo comparado con el de trabajos.
"""
from pulsar.schema import Array, Long, Record, String

TIPO_ACTUALIZADA = 'hogaralpes.acreditacion.actualizada.v1'


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
    # SOLICITADA · ACREDITADA · REVOCADA · VENCIDA
    estado = String(default=None, required_default=True)
    vigente_hasta = String(default=None, required_default=True)
    # Versión del agregado en el event store: es lo que hace idempotente al
    # consumidor. Una versión menor o igual a la almacenada se ignora.
    version = Long(default=None, required_default=True)
