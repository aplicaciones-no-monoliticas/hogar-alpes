"""Sobre común de todo mensaje que sale de un servicio (estilo CloudEvents).

## Por qué aquí no hay una clase base de la que heredar

Se intentó. **No funciona**: el metaclase de `pulsar.schema` construye los campos
mirando únicamente el diccionario propio de la clase
(`RecordMeta._get_fields(dct)` en `pulsar/schema/definition.py:47-65`), así que
**los campos heredados se pierden silenciosamente**. Una clase que solo hereda
—como era `ComandoIntegracion`— produce un esquema con **cero** campos.

No es teoría: el servicio Gestión de Trabajos venía publicando
`EventoTrabajoCreado` con un solo campo, `data`. El sobre nunca viajó, pese a
que la especificación lo daba por existente (`RS-2`). Se descubrió al verificar
CON-1 (`docs/decisiones.md`).

Por eso cada contrato **repite los ocho campos del sobre de forma explícita**.
Es duplicación deliberada, del mismo tipo que el seedwork copiado (`TO-7`): se
prefiere la repetición visible a una herencia que falla en silencio.
`herramientas/verificar_contratos.py` comprueba que los cinco contratos los
lleven, para que la duplicación no se desvíe.

## Los ocho campos

| Campo | Para qué |
|---|---|
| `id` | Identificador del mensaje; es la clave de deduplicación en el consumidor |
| `time` · `ingestion` | Cuándo ocurrió el hecho y cuándo se ingirió |
| `specversion` | Versión de la envolvente |
| `type` | Versión **semántica** del evento: `hogaralpes.trabajo.creado.v1` |
| `datacontenttype` | Formato de la carga |
| `service_name` | Quién lo publicó |
| `correlation_id` | `TO-4`: sin él, un incidente distribuido es inauditable |
"""
import time as _time
import uuid

from pulsar.schema import Long, String  # noqa: F401  (reexportados por comodidad)

CAMPOS_SOBRE = (
    'id',
    'time',
    'ingestion',
    'specversion',
    'type',
    'datacontenttype',
    'service_name',
    'correlation_id',
)

SPEC_VERSION = '1.0'
CONTENT_TYPE = 'application/avro'


def sobre(tipo: str, service_name: str, correlation_id: str | None = None) -> dict:
    """Construye el sobre de un mensaje. Los productores hacen:

        Contrato(**sobre(TIPO_CREADO, 'gestion-trabajos', correlation_id=trabajo_id),
                 trabajo_id=..., ...)
    """
    ahora = int(_time.time() * 1000)
    return {
        'id': str(uuid.uuid4()),
        'time': ahora,
        'ingestion': ahora,
        'specversion': SPEC_VERSION,
        'type': tipo,
        'datacontenttype': CONTENT_TYPE,
        'service_name': service_name,
        'correlation_id': correlation_id or str(uuid.uuid4()),
    }
