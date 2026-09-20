# Contrato HTTP: `saga_log` API

Servicio nuevo, expuesto en `docker-compose.yml` como `saga-log` (puerto host
`${PUERTO_SAGA:-8004}`), ya referenciado por el BFF vía `URL_SAGAS` (sin cambios en el BFF —
ver `research.md` D10). Sin autenticación, igual que el resto de las API internas del sistema.

## `GET /sagas/{trabajo_id}`

Estado y línea de tiempo completa de una transacción (CA-1.12).

**200**
```json
{
  "trabajo_id": "…",
  "correlation_id": "…",
  "estado": "COMPLETADA",
  "iniciada_en": "2026-09-20T10:00:00",
  "terminada_en": "2026-09-20T10:00:04",
  "pasos": [
    {"servicio": "gestion-trabajos", "paso": "hogaralpes.trabajo.creado.v1", "direccion": "AVANCE", "ocurrido_en": "…"},
    {"servicio": "emparejamiento", "paso": "hogaralpes.emparejamiento.proveedor-propuesto.v1", "direccion": "AVANCE", "ocurrido_en": "…"},
    {"servicio": "acreditacion", "paso": "hogaralpes.acreditacion.vigencia-confirmada.v1", "direccion": "AVANCE", "ocurrido_en": "…"},
    {"servicio": "gestion-trabajos", "paso": "hogaralpes.trabajo.estado-cambiado.v1", "direccion": "AVANCE", "ocurrido_en": "…"}
  ]
}
```

**404** — no hay ninguna transacción con ese `trabajo_id`.

## `GET /sagas?estado=`

Todas las transacciones en un estado dado (CA-1.13, FR-012). `estado` acepta los cuatro
persistidos (`EN_CURSO` · `COMPENSANDO` · `COMPLETADA` · `COMPENSADA`) y el calculado
`INCOMPLETA` (ver `research.md` D9 — filtra sobre `EN_CURSO`/`COMPENSANDO` con antigüedad mayor al
umbral).

**200**
```json
[
  {"trabajo_id": "…", "correlation_id": "…", "estado": "COMPLETADA", "iniciada_en": "…", "terminada_en": "…"}
]
```

## `GET /sagas/resumen`

Cuántas transacciones hay en cada estado, de un vistazo (FR-013, y lo que consume
`GET /estado-del-sistema` del BFF).

**200**
```json
{"EN_CURSO": 0, "COMPLETADA": 12, "COMPENSANDO": 0, "COMPENSADA": 3, "INCOMPLETA": 0}
```

## `GET /health`

Igual que el de cualquier otro servicio de la plantilla — sin dependencias externas en la
respuesta (no consulta el broker ni bloquea si Pulsar está caído).

**200** `{"estado": "UP", "servicio": "saga-log"}`
