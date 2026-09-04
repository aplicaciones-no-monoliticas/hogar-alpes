# Escenarios End-to-End (E2E) — guion de demostración

Este documento es el **guion de sustentación**: una lista de escenarios
reproducibles, cada uno diseñado para hacer visible un patrón o una decisión
de arquitectura concreta (ver `docs/PATRONES_DDD.md`). Está pensado para
correrse en vivo frente al evaluador.

Todos los escenarios están automatizados en `scripts/demo_e2e.sh`. Este
documento explica **qué demuestra cada uno y por qué**, para poder narrarlo
mientras el script corre.

---

## Cómo correrlo

```bash
docker compose up --build -d
# esperar ~15s a que Postgres y Pulsar terminen su healthcheck

bash scripts/demo_e2e.sh
```

El script imprime `[OK]` o `[FALLA]` por cada verificación y termina con un
resumen `N/M escenarios superados`. No requiere `jq` ni Python: solo `curl` y
utilidades estándar de shell, para poder correrlo desde cualquier máquina sin
instalar nada adicional.

Variable opcional: `BASE_URL` (por defecto `http://localhost:5000`).

```bash
BASE_URL=http://localhost:5000 bash scripts/demo_e2e.sh
```

---

## Tabla resumen

| # | Escenario | Patrón / decisión que evidencia | Escenario de calidad relacionado |
|---|---|---|---|
| 0 | Salud del servicio | — (smoke test) | — |
| 1 | Crear un trabajo válido | CQS (lado de escritura), Fábrica, Objeto Valor, Evento de dominio | QA7 |
| 2 | Leer el trabajo creado | CQS (lado de lectura) | — |
| 3 | El módulo `operaciones` ya abrió su seguimiento | Comunicación entre módulos por eventos de dominio, evento "gordo" | — |
| 4 | Transición de estado válida | Regla de negocio como objeto (Specification), Objeto Valor `EstadoTrabajo` | QA3 |
| 5 | El seguimiento se actualiza sin que nadie lo pida explícitamente | Evento de dominio "delta", agregados independientes sincronizados por eventos | — |
| 6 | Transición de estado inválida | Regla de negocio rechazando una mutación antes de que llegue a la base de datos | QA3 |
| 7 | Categoría no permitida en la región | Puerto `ServicioReglasRegionales` + adaptador sidecar, dominio agnóstico del país | QA2 |
| 8 | Ubicación incompleta | Regla de negocio de invariante estructural | — |
| 9 | Consulta por estado (colección) | CQS (lado de lectura, filtro) | — |
| 10 | Trabajo inexistente | Manejo de "no encontrado" sin filtrar detalles de infraestructura | — |
| 11 (manual) | Comando asíncrono vía Pulsar | Adaptador de entrada asíncrono, mismo `ejecutar_comando` que el HTTP | QA7 |

---

## Detalle de cada escenario

### 0. Salud del servicio

**Por qué se hace primero:** confirma que Postgres, Pulsar y el servicio
están arriba antes de narrar cualquier otra cosa.

```bash
curl -s http://localhost:5000/health
```

**Esperado:** `200` con `{"status": "up", "service": "gestion-trabajos"}`.

---

### 1. Crear un trabajo válido — CQS, lado de escritura

```bash
curl -s -X POST http://localhost:5000/trabajos \
  -H 'Content-Type: application/json' \
  -d '{
    "canal": "B2B2C", "partner_id": "seguros-alpes", "referencia_externa": "SIN-99123",
    "categoria": "SINIESTRO_GRANIZO", "urgencia": "CRITICA",
    "pais": "CO", "ciudad": "Bogota", "direccion": "Cra 7 # 71-21",
    "descripcion": "Granizada: techo perforado"
  }'
```

**Esperado:** `202 Accepted` con `{"id": "<uuid>", "estado": "CREADO"}`.

**Qué se narra:** un `202`, no un `200` ni un `201` — el comando fue
*aceptado*, no necesariamente terminado de propagar a todo el sistema. Detrás
de este único request ya ocurrieron, en orden: la fábrica construyó el
`Trabajo`, el sidecar regional (`SidecarReglasRegionales`) resolvió qué
categorías aplican en `CO`, las reglas de negocio (`UbicacionCompleta`,
`CategoriaPermitidaEnRegion`, `UrgenciaPermitidaEnRegion`) se validaron, se
generó el evento de dominio `TrabajoCreado`, la Unidad de Trabajo hizo commit,
y **solo entonces** se publicó el evento de integración hacia Pulsar. Ver
`docs/PATRONES_DDD.md`, sección 9, para el recorrido completo.

---

### 2. Leer el trabajo creado — CQS, lado de lectura

```bash
curl -s http://localhost:5000/trabajos/<ID>
```

**Esperado:** `200` con los datos completos, `estado: "CREADO"`.

**Qué se narra:** esta consulta usa un objeto `Query` y un handler totalmente
distinto del comando del escenario 1 (`ObtenerTrabajo`). No hay una sola
clase que "haga las dos cosas" — es CQS aplicado, no solo declarado en el
README.

---

### 3. El módulo `operaciones` ya tiene seguimiento — comunicación por eventos

```bash
curl -s http://localhost:5000/trabajos/<ID>/seguimiento
```

**Esperado:** `200` con `prioridad: "P1"` y `minutos_sla: 60` (porque la
urgencia era `CRITICA`).

**Qué se narra — el momento más importante de la demo:** este endpoint
pertenece al módulo `operaciones`, que **nunca fue invocado directamente**.
`operaciones` construyó este `SeguimientoOperativo` — incluyendo el cálculo
de prioridad, que depende de la urgencia — leyendo únicamente los atributos
del evento de dominio `TrabajoCreado` que `trabajos` emitió en el paso 1. No
hubo ninguna consulta cruzada a la tabla `trabajos`. Esto es lo que en
`docs/PATRONES_DDD.md` (sección 7.5) se explica como un **evento "gordo"**
(event-carried state transfer): el evento trae suficiente información para
que el consumidor actúe solo.

---

### 4. Transición de estado válida

```bash
curl -s -X PUT http://localhost:5000/trabajos/<ID>/estado \
  -H 'Content-Type: application/json' -d '{"estado":"EMPAREJANDO"}'
```

**Esperado:** `202` con `{"id": "<ID>", "estado": "EMPAREJANDO"}`.

**Qué se narra:** la validación de "¿puedo pasar de CREADO a EMPAREJANDO?"
no está en un `if` dentro del handler — vive en el objeto valor
`EstadoTrabajo.puede_transicionar_a`, consultando el grafo `TRANSICIONES`.
Agregar un estado nuevo al ciclo de vida (como ya se hizo con
`EN_VERIFICACION`) se resuelve tocando ese único diccionario.

---

### 5. El seguimiento se actualiza solo

```bash
curl -s http://localhost:5000/trabajos/<ID>/seguimiento
```

**Esperado:** `200` con `estado_trabajo: "EMPAREJANDO"` (cambió respecto al
escenario 3, sin que nadie llamara explícitamente a `operaciones`).

**Qué se narra:** el comando del escenario 4 solo tocó la agregación
`Trabajo`. Fue el evento de dominio `EstadoTrabajoCambiado` — más liviano que
`TrabajoCreado`, trae solo el delta (`estado_anterior`, `estado_nuevo`) — el
que le avisó a `operaciones` que actualizara su propio agregado. Dos
agregados, dos módulos, mantenidos en sincronía sin acoplamiento de código.

---

### 6. Transición de estado inválida — la regla de negocio rechaza antes de tocar la base de datos

```bash
curl -s -X PUT http://localhost:5000/trabajos/<ID>/estado \
  -H 'Content-Type: application/json' -d '{"estado":"COMPLETADO"}'
```

**Esperado:** `409 Conflict` con un `error` describiendo la transición
inválida (el trabajo está en `EMPAREJANDO`, no puede saltar directo a
`COMPLETADO`).

**Qué se narra:** la excepción (`ReglaNegocioExcepcion`) la lanza el
**dominio**, no la capa HTTP. `api/trabajos.py` solo la traduce a un código
de estado. Si mañana este mismo comando llegara por Pulsar en vez de HTTP, la
regla se aplicaría exactamente igual — vive en un solo lugar.

---

### 7. Categoría no permitida en la región — el dominio no sabe en qué país corre

```bash
curl -s -X POST http://localhost:5000/trabajos \
  -H 'Content-Type: application/json' \
  -d '{
    "categoria": "SINIESTRO_GRANIZO", "urgencia": "ALTA",
    "pais": "MX", "ciudad": "CDMX", "direccion": "Reforma 100"
  }'
```

**Esperado:** `400 Bad Request` — `SINIESTRO_GRANIZO` no existe en el
catálogo de México (`reglas_regionales.json`), solo en el de Colombia.

**Qué se narra:** el dominio (`CategoriaPermitidaEnRegion`) no tiene ni un
`if pais == 'MX'`. Recibe una lista de categorías permitidas ya resuelta por
el puerto `ServicioReglasRegionales` y solo pregunta "¿está en la lista?".
Agregar Perú mañana es una entrada nueva en el JSON del sidecar, cero cambios
de código ni redespliegue del dominio.

---

### 8. Ubicación incompleta — invariante estructural

```bash
curl -s -X POST http://localhost:5000/trabajos \
  -H 'Content-Type: application/json' \
  -d '{
    "categoria": "PLOMERIA", "urgencia": "NORMAL",
    "pais": "CO", "ciudad": "", "direccion": ""
  }'
```

**Esperado:** `400 Bad Request` — la regla `UbicacionCompleta` exige país,
ciudad y dirección.

---

### 9. Consulta por estado (colección)

```bash
curl -s "http://localhost:5000/trabajos?estado=CREADO"
```

**Esperado:** `200` con un arreglo JSON (puede estar vacío si ya no queda
ningún trabajo en `CREADO`, según lo que dejaron los escenarios previos).

**Qué se narra:** mismo mecanismo de `Query`/`ejecutar_query` que el
escenario 2, pero con un handler distinto (`ObtenerTrabajosPorEstado`) — cada
pregunta de negocio tiene su propia clase, no un único método genérico con
parámetros opcionales.

---

### 10. Trabajo inexistente

```bash
curl -s http://localhost:5000/trabajos/00000000-0000-0000-0000-000000000000
```

**Esperado:** `404 Not Found`.

**Qué se narra:** el repositorio devuelve `None` (un detalle de
infraestructura) y es el handler de la query quien lo traduce a "no
encontrado" — la ausencia de un dato no es una excepción, es un resultado
válido y esperado del `QueryResultado`.

---

### 11. (Manual, opcional) Comando asíncrono vía Pulsar

No se automatiza en el script porque `curl` no habla el protocolo binario de
Pulsar. Para demostrarlo en vivo:

1. Levantar el stack con el consumidor activo:
   `CONSUMIR_COMANDOS=true` ya está seteado en `docker-compose.yml`.
2. Publicar un mensaje Avro en el tópico `cmd-trabajo` con un cliente Pulsar
   (Python, usando el mismo esquema que `infraestructura/schema/v1/comandos.py`).
3. Observar en los logs del contenedor `gestion-trabajos` la línea
   `Comando recibido: ...` (emitida por `infraestructura/consumidores.py`) y
   luego confirmar con `GET /trabajos?estado=CREADO` que el trabajo se creó
   sin que nadie llamara al endpoint HTTP.

**Qué se narra:** el adaptador de entrada asíncrono
(`suscribirse_a_comandos`, corriendo en un hilo daemon separado) llama al
**mismo** `ejecutar_comando(comando)` que usa `api/trabajos.py`. La capa de
aplicación no distingue si el comando llegó por HTTP o por una cola — es la
prueba de que el puerto de entrada está bien definido y desacoplado del
protocolo de transporte.

---

## Qué NO cubre este guion (limitaciones conocidas)

- No verifica que el evento de **integración** efectivamente haya llegado al
  tópico `evt-trabajo` de Pulsar (requeriría un consumidor de prueba
  suscrito a ese tópico). Se puede confirmar manualmente con
  `pulsar-admin topics stats persistent://public/default/evt-trabajo`
  dentro del contenedor de Pulsar.
- No prueba concurrencia ni el comportamiento bajo el pico ×4 del escenario de
  calidad 7 — solo prueba que la ruta asíncrona existe y funciona
  funcionalmente.
- No incluye limpieza de datos entre corridas: cada ejecución del script crea
  trabajos nuevos. No afecta la validez de las verificaciones, pero la base
  de datos acumula registros de demostración.
