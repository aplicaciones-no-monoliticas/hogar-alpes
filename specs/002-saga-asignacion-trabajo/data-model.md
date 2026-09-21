# Data Model: Saga de asignación de un trabajo

Ver decisiones en `research.md` (D1–D9) para el porqué de cada tabla. Este documento describe el
**qué**: entidades, atributos y transiciones, por servicio.

## Gestión de Trabajos (`servicios/gestion_trabajos`)

### Trabajo (agregación existente, extendida)

`modulos/trabajos/dominio/entidades.py` — cambio: **un atributo nuevo**.

| Atributo | Tipo | Nota |
|---|---|---|
| `proveedor_id` | `str \| None` | Nuevo (D5). `None` hasta que la saga completa; se fija junto con la transición a `ASIGNADO`. Se limpia (`None`) si el trabajo se cancela después de haber estado asignado — fuera de alcance de esta historia (ver Assumptions del spec), así que en la práctica solo se fija una vez. |
| *(resto sin cambios)* | | `solicitante`, `categoria`, `urgencia`, `ubicacion`, `descripcion`, `estado`, `sub_trabajos` |

Transición nueva que la saga dispara (las demás ya existían en `TRANSICIONES`):

```
CREADO ──(crear, ya existe)──> EMPAREJANDO ──(vigencia confirmada)──> ASIGNADO
                                    │
                                    ├──(sin candidatos)────────> CANCELADO
                                    ├──(vigencia rechazada)────> CANCELADO
                                    └──(falla asignación final)─> CANCELADO
```

`CREADO → EMPAREJANDO` la dispara el propio `CrearTrabajoHandler`, en el mismo commit que crea el
trabajo (no espera un mensaje externo: es la forma de que `evt-trabajo` porte el estado correcto
desde el primer momento en que Emparejamiento lo lee).

Tabla `trabajos` (`infraestructura/dto.py`): **una columna nueva**, `proveedor_id VARCHAR(40)
NULL`.

## Emparejamiento (`servicios/emparejamiento`)

### Emparejamiento (agregación existente, extendida)

`modulos/emparejamiento/dominio/entidades.py` — un atributo nuevo:

| Atributo | Tipo | Nota |
|---|---|---|
| `candidatos` | `list[Candidato]` | Sin cambios: sigue siendo la lista completa, para no romper `GET /candidatos` ni `GET /emparejamientos/{id}` |
| `proveedor_reservado` | `str \| None` | Nuevo. El único candidato que efectivamente logró reservarse para este trabajo. `None` si la lista estaba vacía o si ningún candidato de la lista pudo reservarse (equivalente a sin candidatos para la saga) |

### Reserva de proveedor (entidad nueva, tabla nueva)

Modela la relación temporal proveedor↔trabajo de la especificación (Key Entities del spec).

Tabla `reservas_proveedor` (`infraestructura/dto.py`):

| Columna | Tipo | Nota |
|---|---|---|
| `proveedor_id` | `VARCHAR(40)` PK | La restricción de unicidad que resuelve R5-2 (D1) |
| `trabajo_id` | `VARCHAR(40)` NOT NULL, indexado | Para liberar por trabajo al compensar |
| `categoria` | `VARCHAR(40)` NOT NULL | Auditoría/depuración |
| `reservado_en` | `TIMESTAMP` NOT NULL | Auditoría |

Ciclo de vida: se crea al reservar (paso 2 de ida), se borra al compensar (reversión del paso 2) o
queda para siempre si la saga completa (el proveedor sigue "ocupado" por este trabajo — revocar esa
ocupación cuando el trabajo termine es la saga D, fuera de alcance, ver Assumptions).

## Acreditación (`servicios/acreditacion`)

### Vigencia por proveedor (proyección de lectura nueva, interna del servicio)

No es una agregación ni pasa por Event Sourcing: es una tabla derivada, actualizada junto con cada
evento que ya se escribe en `eventos_acreditacion` (D4).

Tabla `vigencia_por_proveedor` (`infraestructura/dto.py`):

| Columna | Tipo | Nota |
|---|---|---|
| `proveedor_id` | `VARCHAR(40)` | PK compuesta con `categoria` |
| `categoria` | `VARCHAR(40)` | PK compuesta con `proveedor_id` — un proveedor puede tener varias categorías, igual que en la proyección de Emparejamiento |
| `estado` | `VARCHAR(20)` | `SOLICITADA` · `ACREDITADA` · `REVOCADA` · `VENCIDA` |
| `vigente_hasta` | `VARCHAR(10)` | ISO-8601, comparable como texto (igual que en Emparejamiento) |
| `version` | `INTEGER` | Tolerante al desorden: solo se actualiza si `version` > la almacenada |

## `saga_log` (servicio nuevo)

Ver D9 para el ciclo de derivación del estado. No hay agregación de dominio ni Event Sourcing: es
un servicio de solo lectura sobre lo que observa, así que sus tablas son directamente el modelo de
persistencia (no hay una capa de dominio con reglas de negocio que proteger, más allá de la
deduplicación).

### Transacción de saga

Tabla `transacciones_saga`:

| Columna | Tipo | Nota |
|---|---|---|
| `trabajo_id` | `VARCHAR(40)` PK | Clave de negocio (spec: Key Entities → Transacción de asignación) |
| `correlation_id` | `VARCHAR(64)` indexado | Clave de traza |
| `estado` | `VARCHAR(20)` | `EN_CURSO` · `COMPLETADA` · `COMPENSANDO` · `COMPENSADA` (`INCOMPLETA` es calculado, no almacenado — D9) |
| `iniciada_en` | `TIMESTAMP` | Momento del primer paso visto |
| `terminada_en` | `TIMESTAMP NULL` | Momento del paso que llevó a `COMPLETADA`/`COMPENSADA` |

### Paso de la transacción

Tabla `pasos_saga`:

| Columna | Tipo | Nota |
|---|---|---|
| `id` | `VARCHAR(40)` PK | UUID propio de la fila |
| `mensaje_id` | `VARCHAR(40)` UNIQUE | El campo `id` del sobre CloudEvents del mensaje observado — clave de deduplicación (CA-1.14) |
| `trabajo_id` | `VARCHAR(40)` indexado, FK lógica a `transacciones_saga` | |
| `correlation_id` | `VARCHAR(64)` | Redundante con la transacción, para poder listar pasos sin join si hace falta |
| `servicio` | `VARCHAR(40)` | `gestion-trabajos` · `emparejamiento` · `acreditacion` |
| `paso` | `VARCHAR(80)` | El `type` del mensaje observado, tal cual (p. ej. `hogaralpes.emparejamiento.proveedor-propuesto.v1`) |
| `direccion` | `VARCHAR(10)` | `AVANCE` \| `REVERSION` — derivado del `type` con una tabla de mapeo fija en el código, no persistida como configuración |
| `ocurrido_en` | `TIMESTAMP` | El `time` del sobre (cuándo pasó), no `ingestion` (cuándo lo vio `saga_log`) |

## Contratos de mensajería — resumen de campos nuevos

Ver `contracts/` para el detalle campo por campo. Resumen de qué esquema Avro gana qué, siempre
como campo opcional al final (`default=None, required_default=True`, regla de INF-0):

| Contrato | Campo nuevo | Para qué |
|---|---|---|
| `evt_emparejamiento.py` (`EventoEmparejamiento`) | `proveedor_id: String` | El único proveedor propuesto/liberado (los tipos `candidatos-identificados`/`sin-candidatos` existentes lo dejan vacío) |
| `evt_emparejamiento.py` (`EventoEmparejamiento`) | `motivo: String` | Por qué se liberó (`VIGENCIA_RECHAZADA` · `ASIGNACION_FALLIDA` · `SIN_CANDIDATOS`), para que `saga_log` no tenga que inferirlo |
| `evt_acreditacion.py` (`AcreditacionActualizada`) | `trabajo_id: String` | Ver D8. Vacío en el tipo `actualizada` existente |
| `evt_acreditacion.py` (`AcreditacionActualizada`) | `categoria: String` | La categoría contra la que se evaluó la propuesta (el snapshot ya trae `categorias` en plural; el paso de saga necesita LA categoría del trabajo, singular) |

Ningún campo se quita ni cambia de tipo o de significado; ningún contrato requiere `-v2` (regla de
evolución compatible, Principio II).
