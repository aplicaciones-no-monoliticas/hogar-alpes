# Contrato: `evt-acreditacion` (extendido)

Tópico existente, sin cambios de topología. Clave de partición: `proveedor_id` (sin cambios — el
orden que importa sigue siendo el de un mismo proveedor, no el de un mismo trabajo; la saga tolera
que sus dos mensajes nuevos no tengan orden garantizado entre trabajos distintos porque cada uno se
procesa por su propio `trabajo_id`).

Archivo canónico: `contratos/v1/evt_acreditacion.py`.

## Campos (los 8 del sobre sin cambios + carga)

| Campo | Tipo Avro | Nuevo | Nota |
|---|---|---|---|
| *(8 campos del sobre)* | — | No | |
| `acreditacion_id` | `String` | No | |
| `proveedor_id` | `String` | No | |
| `pais` | `String` | No | |
| `ciudad` | `String` | No | |
| `categorias` | `Array<String>` | No | Todas las categorías del proveedor (snapshot) |
| `nivel` | `String` | No | |
| `estado` | `String` | No | `SOLICITADA` · `ACREDITADA` · `REVOCADA` · `VENCIDA` |
| `vigente_hasta` | `String` | No | |
| `version` | `Long` | No | |
| `trabajo_id` | `String` | **Sí** | `default=''`. Ver D8 de `research.md`. Vacío en `actualizada` (no pertenece a ninguna saga) |
| `categoria` | `String` | **Sí** | `default=''`. LA categoría (singular) contra la que se evaluó la propuesta de esta saga. Vacío en `actualizada` |

## Tipos de mensaje (`type`)

| Constante | Valor | Cuándo se publica | Es reversión de |
|---|---|---|---|
| `TIPO_ACTUALIZADA` | `hogaralpes.acreditacion.actualizada.v1` | Sin cambios: snapshot completo en cada `solicitar`/`aprobar`/`revocar` | — |
| `TIPO_VIGENCIA_CONFIRMADA` (nuevo) | `hogaralpes.acreditacion.vigencia-confirmada.v1` | Al recibir `proveedor-propuesto`, si `vigencia_por_proveedor(proveedor_id, categoria)` está `ACREDITADA` y no vencida (paso 3 de ida) | — |
| `TIPO_VIGENCIA_RECHAZADA` (nuevo) | `hogaralpes.acreditacion.vigencia-rechazada.v1` | Al recibir `proveedor-propuesto`, si no está vigente, o si la marca de simulación `VIGENCIA` está presente | `vigencia-confirmada` |

## Quién consume qué (nuevo)

| Consumidor | Suscripción | Tipos que le importan | Tipos que ignora |
|---|---|---|---|
| Emparejamiento (nuevo, distinto de `emparejamiento-proyeccion`) | `emparejamiento-saga` (Shared) | `vigencia-rechazada` | `actualizada`, `vigencia-confirmada` |
| Gestión de Trabajos (nuevo) | `gestion-trabajos-saga` (Shared) | `vigencia-confirmada`, `vigencia-rechazada` | `actualizada` |
| `saga_log` (nuevo) | `saga-log` (Shared) | los tres | ninguno propio (descarta lo que no reconozca) |

**R5-1, aceptado explícitamente**: la suscripción nueva de Gestión de Trabajos sobre
`evt-acreditacion` también recibe los mensajes `actualizada` de la carga masiva del escenario de
escalabilidad (Entrega 4). El descarte es por `type` (comparación de texto, sin decodificar el
resto del mensaje) antes de tocar ninguna lógica de negocio — el mismo costo que ya paga
Emparejamiento hoy en su propia suscripción de proyección.
