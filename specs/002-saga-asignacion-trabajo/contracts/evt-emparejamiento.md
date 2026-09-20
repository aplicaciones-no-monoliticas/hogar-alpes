# Contrato: `evt-emparejamiento` (extendido)

Tópico existente, sin cambios de topología. Clave de partición: `trabajo_id` (sin cambios).

Archivo canónico: `contratos/v1/evt_emparejamiento.py`, copiado a
`servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/infraestructura/schema/v1/evt_emparejamiento.py`
y leído (no copiado, solo importados los `TIPO_*` y la clase) desde
`servicios/gestion_trabajos/.../schema/v1/` y `servicios/acreditacion/.../schema/v1/` como sus
propias copias locales del mismo contrato (regla de `TO-7`: se copia, no se comparte en tiempo de
compilación).

## Campos (los 8 del sobre sin cambios + carga)

| Campo | Tipo Avro | Nuevo | Nota |
|---|---|---|---|
| *(8 campos del sobre)* | — | No | Sin cambios — ver `contratos/v1/mensajes.py` |
| `trabajo_id` | `String` | No | Sin cambios |
| `region` | `String` | No | Sin cambios |
| `categoria` | `String` | No | Sin cambios |
| `pais` | `String` | No | Sin cambios |
| `ciudad` | `String` | No | Sin cambios |
| `total_candidatos` | `Long` | No | Sin cambios |
| `candidatos` | `Array<String>` | No | Sin cambios. Sigue llevando la lista COMPLETA de candidatos elegibles (no solo el reservado), para no romper `GET /candidatos` |
| `proveedor_id` | `String` | **Sí** | `default=''`. El proveedor efectivamente propuesto/reservado (o liberado). Vacío en `candidatos-identificados`/`sin-candidatos` |
| `motivo` | `String` | **Sí** | `default=''`. Solo en `candidatos-liberados`: `VIGENCIA_RECHAZADA` \| `ASIGNACION_FALLIDA` \| `SIN_CANDIDATOS` |

## Tipos de mensaje (`type`)

| Constante | Valor | Cuándo se publica | Es reversión de |
|---|---|---|---|
| `TIPO_CANDIDATOS` | `hogaralpes.emparejamiento.candidatos-identificados.v1` | Sin cambios: existe hoy, sigue publicándose igual (lista completa) | — |
| `TIPO_SIN_CANDIDATOS` | `hogaralpes.emparejamiento.sin-candidatos.v1` | Sin cambios en el disparador (no hay candidatos elegibles), pero AHORA además dispara compensación en GT (antes nadie lo consumía) | — |
| `TIPO_PROVEEDOR_PROPUESTO` (nuevo) | `hogaralpes.emparejamiento.proveedor-propuesto.v1` | Tras reservar exitosamente un candidato de la lista (paso 2 de ida) | — |
| `TIPO_CANDIDATOS_LIBERADOS` (nuevo) | `hogaralpes.emparejamiento.candidatos-liberados.v1` | Al liberar la reserva (vigencia rechazada, o falla en la asignación final) | `proveedor-propuesto` |

## Quién consume qué (nuevo)

| Consumidor | Suscripción | Tipos que le importan | Tipos que ignora |
|---|---|---|---|
| Acreditación (nuevo) | `acreditacion` (Shared) | `proveedor-propuesto` | `candidatos-identificados`, `sin-candidatos`, `candidatos-liberados` |
| Gestión de Trabajos (nuevo) | `gestion-trabajos-saga` (Shared) | `sin-candidatos` | `candidatos-identificados`, `proveedor-propuesto`, `candidatos-liberados` |
| `saga_log` (nuevo) | `saga-log` (Shared) | los cuatro | ninguno propio del servicio (pero descarta cualquier `type` que no reconozca) |
