# Research: Saga de asignación de un trabajo

**Input**: `docs/us-entrega-5/US-01-saga-asignacion-de-trabajo.md` (documento de diseño ya
aprobado a nivel de negocio) + inspección directa del código de `gestion_trabajos`,
`emparejamiento`, `acreditacion`, `bff`, `contratos/v1/`, `infra/pulsar/` y `docs/decisiones.md`.

No hay "NEEDS CLARIFICATION" pendiente: el US-01 ya resuelve la mayoría de las decisiones de
producto. Este documento resuelve las decisiones **técnicas** que el US-01 deja abiertas o que
solo se ven leyendo el código actual.

---

## D1 — Cómo Emparejamiento reserva UN proveedor (no una lista)

**Decisión**: Emparejamiento sigue calculando la lista completa de candidatos exactamente igual
que hoy (`RepositorioProveedoresCandidatos.buscar`), y sigue persistiendo esa lista completa en
`emparejamientos.candidatos` para no romper `GET /candidatos` ni `GET /emparejamientos/{id}`
(CA-1.18/CA-1.19, cero regresión). Lo nuevo es un paso adicional: de esa lista, intenta reservar
proveedores **en orden** hasta que uno se deje reservar, insertando una fila en una tabla nueva
`reservas_proveedor(proveedor_id PK, trabajo_id, categoria, reservado_en)`. La clave primaria en
`proveedor_id` es la restricción de unicidad que resuelve R5-2: dos trabajos que compiten por el
mismo proveedor casi al tiempo — el segundo `INSERT` falla con `IntegrityError`, ese trabajo
prueba el siguiente candidato de su propia lista, y si se agota la lista sin reservar a nadie,
es equivalente a "sin candidatos" para efectos de la saga.

**Rationale**: Reutiliza el patrón ya usado en Acreditación (`UNIQUE(agregado_id, version)` +
`try/except IntegrityError` + `db.session.flush()` para detectar el conflicto de inmediato, no en
un commit posterior). No toca el modelo de lectura existente.

**Alternativas consideradas**:
- Añadir una columna `trabajo_id nullable` a `proveedores_candidatos` (la proyección). Rechazada:
  mezclaría el estado de la proyección (alimentada solo por `evt-acreditacion`, tolerante al
  desorden) con el estado de una reserva transaccional de la saga; un evento de acreditación fuera
  de orden podría pisar una reserva viva.
- Bloqueo optimista sobre la fila del proveedor. Rechazada: no hay una fila "del proveedor" que
  tenga sentido bloquear sin introducir la tabla nueva de todas formas.

**Liberar la reserva**: al compensar, se borra la fila de `reservas_proveedor` por `proveedor_id`
(o por `trabajo_id`, ambos son claves válidas de búsqueda). Un `DELETE` de una fila que ya no
existe (reentrega) es un no-op — idempotente por construcción (FR-016).

---

## D2 — Qué campo distingue avance de reversión en cada mensaje nuevo

**Decisión**: Ningún tópico nuevo (FR-018, CA-1.7). Cada paso y su reversión son un **valor nuevo
del campo `type`** sobre el stream que ya existe, exactamente como ya lo hacen
`TIPO_CREADO`/`TIPO_ESTADO_CAMBIADO` en `evt-trabajo` o `SOLICITAR`/`APROBAR`/`REVOCAR` en
`cmd-acreditacion`. Los consumidores existentes que no reconocen un `type` nuevo lo ignoran
(`if valor.type != ESPERADO: return`), patrón ya usado en
`emparejamiento/infraestructura/consumidores.py::manejar_evento_trabajo` (CA-1.10).

Streams tocados y sus `type` nuevos:

| Stream | `type` nuevo | Reemplaza/complementa | Reversión de |
|---|---|---|---|
| `evt-emparejamiento` | `hogaralpes.emparejamiento.proveedor-propuesto.v1` | Nuevo, además de `candidatos-identificados` (que se conserva para `GET /candidatos`) | — (paso 2 de ida) |
| `evt-emparejamiento` | `hogaralpes.emparejamiento.candidatos-liberados.v1` | Nuevo | `proveedor-propuesto` |
| `evt-acreditacion` | `hogaralpes.acreditacion.vigencia-confirmada.v1` | Nuevo, además de `actualizada` (snapshot, sin tocar) | — (paso 3 de ida) |
| `evt-acreditacion` | `hogaralpes.acreditacion.vigencia-rechazada.v1` | Nuevo | `vigencia-confirmada` |

`evt-trabajo` no necesita un `type` nuevo: la asignación y la cancelación ya son
`TIPO_ESTADO_CAMBIADO` con `estado='ASIGNADO'` o `estado='CANCELADO'` — son datos, no un tipo de
mensaje distinto, y las transiciones `EMPAREJANDO→ASIGNADO`/`EMPAREJANDO→CANCELADO` ya son válidas
en `TRANSICIONES` (`objetos_valor.py`). Sí hace falta una transición nueva **desde** `CREADO`: hoy
nada mueve un trabajo a `EMPAREJANDO`. `CrearTrabajoHandler` debe hacerlo explícitamente tras
`trabajo.crear(...)` (mismo commit, mismo evento de creación ya cubre CA-1.2 sin publicar un evento
de integración adicional — o si se prefiere visibilidad en el registro de sagas, un
`EstadoTrabajoCambiado` adicional `CREADO→EMPAREJANDO` inmediatamente después de crear).

**Rationale**: es la regla que el propio US-01 fija (tabla "Los pasos y sus reversiones") y la que
ya sigue todo el sistema para evolucionar sin romper contratos (Principio II).

---

## D3 — Cómo viaja la marca de simulación de fallos (`SIMULAR_FALLO`)

**Decisión**: **Propiedad del mensaje de Pulsar**, nunca un campo Avro. `despachadores.py` ya
tiene el mecanismo (`propiedades={...}` además de `properties['correlation_id']`); se añade
`propiedades['simular_fallo'] = valor` cuando el comando que originó la cadena la trae. Se lee con
`(mensaje.properties() or {}).get('simular_fallo')`, igual que ya se lee `correlation_id` en
`correlacion.desde_mensaje`. La marca entra por `POST /trabajos` como campo JSON opcional
`simular_fallo` (valores: `SIN_CANDIDATOS` · `VIGENCIA` · `ASIGNACION`, ausente = flujo normal),
GT la agrega como propiedad al publicar `cmd-trabajo`/`evt-trabajo`, y cada servicio que reenvía un
mensaje de la cadena copia la propiedad sin interpretarla salvo el que decide con ella.

**Rationale**: cumple literalmente lo que pide el US-01 ("se puede leer sin descifrar el mensaje,
no obliga a cambiar la forma de ningún contrato") y no toca ningún esquema Avro para una
herramienta de demostración que además el propio US-01 dice que no debe documentarse como
funcionalidad del producto.

**Dónde decide cada marca**:
- `SIN_CANDIDATOS`: `EmparejarTrabajoHandler` ve la propiedad y publica `SinCandidatos` sin
  siquiera consultar la proyección.
- `VIGENCIA`: el handler de Acreditación que atiende `proveedor-propuesto` ve la propiedad y
  publica `vigencia-rechazada` sin consultar el event store, sin importar el estado real del
  proveedor.
- `ASIGNACION`: el handler de GT que atiende `vigencia-confirmada` ve la propiedad, no asigna, y en
  su lugar publica `EstadoTrabajoCambiado` a `CANCELADO` (equivalente a "falla la asignación
  final").

---

## D4 — Cómo Acreditación resuelve "¿este proveedor sigue vigente para esta categoría?"

**Decisión**: Acreditación es Event Sourcing puro, indexado por `agregado_id` (el
`acreditacion_id`), no por `proveedor_id`. La consulta que la saga necesita —dado un
`proveedor_id` y una `categoria`, ¿su acreditación vigente es `ACREDITADA` y no venció?— no existe
hoy. Se añade una tabla de **proyección de lectura interna**, propia de Acreditación (no
compartida con la de Emparejamiento, que es una copia independiente por diseño):
`vigencia_por_proveedor(proveedor_id, categoria, estado, vigente_hasta, version)`, con
`PRIMARY KEY(proveedor_id, categoria)`. Se actualiza con un `upsert` tolerante al desorden
(`version` mayor gana) desde el mismo lugar donde hoy se registran los eventos del agregado
(`RepositorioAcreditacionesEventSourcing.agregar`), en la misma transacción — no es un consumidor
nuevo, es una escritura adicional junto al *event store*.

**Rationale**: mantiene el Event Sourcing como fuente de verdad para escritura y auditoría
(`GET /acreditaciones/{id}/eventos` no cambia), y da una lectura por `proveedor_id` en <1 consulta,
igual de barata que la proyección que ya tiene Emparejamiento, sin acoplar los dos servicios ni
inventar una lectura sobre JSON no indexado.

**Alternativas consideradas**: consultar `eventos_acreditacion.datos` con un filtro JSON sobre
`proveedor_id` y quedarse con el de mayor `version`. Rechazada: sin índice sobre una columna JSON
sería un *table scan* por cada propuesta de la saga; con más de 100.000 proveedores (meta de
calidad de la Entrega 4) no cumple el objetivo de latencia.

---

## D5 — El trabajo necesita saber a quién quedó asignado

**Decisión**: se agrega `proveedor_id: str | None` a la agregación `Trabajo`
(`dominio/entidades.py`), a `TrabajoDTO` (`aplicacion/dto.py`), a la tabla `trabajos`
(`infraestructura/dto.py`, columna nueva `nullable=True`) y a la respuesta de
`GET /trabajos/{id}` (`MapeadorTrabajoDTOJson.dto_a_externo`). Se fija en el mismo handler que
procesa `vigencia-confirmada` y transiciona el trabajo a `ASIGNADO`.

**Rationale**: es exactamente lo que pide CA-1.1 ("el identificador del proveedor asignado visible
al consultarlo") y no requiere una tabla nueva ni un evento de dominio nuevo — es un atributo más
de la transición `EstadoTrabajoCambiado`.

---

## D6 — Las tres suscripciones nuevas necesitan pre-crearse en la infraestructura

**Decisión**: la Regla V de la constitución ("las suscripciones MUST pre-crearse") aplica igual a
las suscripciones nuevas. `infra/pulsar/inicializar.sh` y `infra/pulsar/comun.sh` ganan:

| Tópico | Suscripción nueva | Consumidor | Tipo |
|---|---|---|---|
| `evt-emparejamiento` | `gestion-trabajos-saga` | GT (sin candidatos → cancelar) | Shared |
| `evt-emparejamiento` | `acreditacion` | Acreditación (proveedor propuesto) | Shared |
| `evt-acreditacion` | `gestion-trabajos-saga` | GT (vigencia confirmada/rechazada → asignar/cancelar) | Shared |
| `evt-acreditacion` | `emparejamiento-saga` | Emparejamiento (vigencia rechazada → liberar reserva) | Shared |
| `evt-trabajo-{región}` × región | `saga-log` | `saga_log` (los cuatro pasos que pasan por este stream) | Shared, por patrón `evt-trabajo-.*` |
| `evt-emparejamiento` | `saga-log` | `saga_log` | Shared |
| `evt-acreditacion` | `saga-log` | `saga_log` | Shared |

Se usa `Shared` (no `Failover`) en todas: ninguna de estas suscripciones necesita orden entre
mensajes de *distintos* trabajos, y el orden dentro de un mismo trabajo ya lo garantiza la clave de
partición (`trabajo_id` en `evt-trabajo`/`evt-emparejamiento`) más la idempotencia del handler —
igual que la suscripción `gestion-trabajos` sobre `cmd-trabajo-.*` hoy.

**Rationale**: sin esto, un mensaje publicado antes de que el servicio nuevo (o la suscripción
nueva de un servicio existente) arranque por primera vez no se retiene para nadie (mismo defecto
que motivó INF-3).

**Consecuencia sobre `agregar-region.sh`**: `evt-trabajo-{región}` es por región; `saga-log` cubre
todas las regiones existentes y futuras con un patrón (`evt-trabajo-.*`), como ya hace GT para
`cmd-trabajo-.*`, así que **no** hace falta tocar `crear_region()` — la suscripción de `saga-log`
no depende de la región.

---

## D7 — `correlation_id` no necesita corregirse: ya viaja bien

**Decisión**: contrario a lo que asumía la primera lectura del US-01 ("Hoy Gestión de Trabajos y
Emparejamiento usan el identificador del trabajo... Acreditación el del proveedor"), esa brecha
**ya se cerró** en la entrega del BFF (`docs/decisiones.md`, sección "US-02 · BFF y trazabilidad
por petición", punto 9): `correlation_id` dejó de ser `trabajo_id`/`proveedor_id` y es un
identificador por petición que crea el BFF (o cualquier consumidor que reciba un mensaje sin uno
válido) y que viaja intacto por sobre + propiedad del mensaje
(`seedwork/infraestructura/correlacion.py`, idéntico en los cuatro servicios y el BFF). No se
necesita ningún cambio de código para CA-1.11.

**Restricción explícita ya registrada** (`docs/decisiones.md`, mismo punto 9): *"la saga no debe
usar `correlation_id` como clave del trabajo; usa `trabajo_id`"*. Esta decisión de investigación
adopta esa restricción sin más debate: `saga_log` correlaciona por `trabajo_id` (clave de negocio,
partición) **y** por `correlation_id` (clave de traza, para los pasos de Acreditación que no
llevan `trabajo_id` en su carga hoy — ver D8).

---

## D8 — Cómo `saga_log` une pasos que no traen `trabajo_id`

**Decisión**: los mensajes de `evt-acreditacion` (tanto el `actualizada` existente como los dos
nuevos de la saga) llevan `proveedor_id`, no `trabajo_id`, en su carga — excepto los dos nuevos
tipos de saga (`vigencia-confirmada`/`vigencia-rechazada`), a los que se les agrega
`trabajo_id: String(default=None, required_default=True)` como campo nuevo al final del esquema
(evolución compatible, regla de INF-0). Con eso, `saga_log` puede indexar sus pasos por
`trabajo_id` cuando el mensaje lo trae, y por `correlation_id` siempre. Los mensajes de
`evt-acreditacion` que **no** pertenecen a una saga (`AcreditacionActualizada`, la snapshot que ya
existía) llegan sin `trabajo_id` (cadena vacía) y `saga_log` los descarta silenciosamente por
`type` desconocido para su propósito (Edge case: "tipo de mensaje que no puede asociar a ninguna
transacción conocida").

**Rationale**: agregar `trabajo_id` al mensaje de acreditación de la saga es más simple y más
barato en tiempo de consulta que depender solo de `correlation_id` para unir con Gestión de
Trabajos y Emparejamiento, y es coherente con que la clave de negocio de la saga (`GET
/sagas/{trabajo_id}`) sea justamente esa.

---

## D9 — `saga_log` nace de la plantilla, con dos tablas y sin productor

**Decisión**: se copia `servicios/_plantilla/` completa (Dockerfile, seedwork, `correlacion.py`
byte-idéntico) — es la única forma de nacer que aprueba la constitución (Principio III). No se usa
`seedwork/infraestructura/despachadores.py` de la copia (se borra o se deja sin invocar): el
servicio **no publica**, para que CA-1.16 sea verificable revisando que no existe ningún
`pulsar.Client().create_producer(...)` en su código.

Dos tablas (`infraestructura/dto.py`):
- `transacciones_saga(trabajo_id PK, correlation_id indexado, estado, iniciada_en, terminada_en)`
- `pasos_saga(id PK, trabajo_id FK, mensaje_id UNIQUE, servicio, paso, direccion [AVANCE|REVERSION], ocurrido_en)`

`mensaje_id` (el campo `id` del sobre CloudEvents, único por mensaje publicado) es la clave de
deduplicación: un `INSERT ... ON CONFLICT (mensaje_id) DO NOTHING` (o un `try/except
IntegrityError`) hace que una reentrega del broker no duplique un paso (CA-1.14, FR-016) sin
necesitar `SELECT` previo.

**Estado de la transacción** se deriva del último paso visto, con esta tabla de transición (no hay
máquina de estados explícita más allá de esto):

| Paso recibido | Estado resultante |
|---|---|
| `trabajo.creado` (o el `estado-cambiado` a `EMPAREJANDO`) | `EN_CURSO` |
| `estado-cambiado` a `ASIGNADO` | `COMPLETADA`, se fija `terminada_en` |
| `emparejamiento.sin-candidatos` (sin propuesta previa) | `COMPENSADA` directo (no hay nada que deshacer), `terminada_en` |
| `acreditacion.vigencia-rechazada` · `emparejamiento.candidatos-liberados` | `COMPENSANDO` |
| `estado-cambiado` a `CANCELADO` | `COMPENSADA`, `terminada_en` |

`INCOMPLETA` (FR-014, edge case de "nunca llega a un estado final") **no** la calcula el
consumidor al vuelo: es una consulta (`GET /sagas?estado=INCOMPLETA`) que compara
`iniciada_en < ahora - UMBRAL` sobre las filas todavía en `EN_CURSO`/`COMPENSANDO`, con `UMBRAL`
configurable (variable de entorno, valor por defecto generoso, p. ej. 60s — muy por encima de la
latencia de punta a punta esperada). Es una vista calculada, no un estado persistido: mantiene la
constitución de "no participa en ninguna decisión de negocio", solo en cómo se presenta una
consulta.

**Rationale**: reutiliza el mismo patrón "una imagen, dos procesos" (API + consumidor) que ya usan
los otros cuatro servicios, así que el Dockerfile, `docker-compose.yml` y el pipeline de
despliegue (US-03) no necesitan un caso especial.

---

## D10 — El BFF no cambia

**Decisión**: no se toca `servicios/bff/`. Ya tiene: `URL_SAGAS` en `config.py`, las rutas
`GET /sagas/{id}` · `GET /sagas` · `GET /sagas/resumen` en `rutas.py`, el endpoint compuesto
`POST /trabajos/asignacion` que crea el trabajo y devuelve `seguimiento_saga` en `compuestos.py`, y
`saga-log` como quinto servicio en `/estado-del-sistema` y en `/trabajos/{id}/completo`. El campo
`simular_fallo` del cuerpo JSON de `POST /trabajos` pasa sin cambios porque el BFF reenvía el
cuerpo tal cual (`reenvio.reenviar`), sin inspeccionarlo.

**Rationale**: confirmado leyendo el código fuente del BFF — fue construido en la entrega anterior
anticipando exactamente esta historia. Evita trabajo y riesgo de regresión en un servicio que ya
tiene 110 pruebas en verde.
