# Implementation Plan: BFF — un solo punto de entrada y trazabilidad por petición

**Branch**: `001-bff-entry-point` | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-bff-entry-point/spec.md` (origen: `docs/us-entrega-5/US-02-bff.md`)

## Summary

Se agrega un componente de borde, `servicios/bff/` (Flask + gunicorn, sin base de datos y sin broker), que:

1. **Reenvía** las 17 rutas de los cinco servicios de dominio con la misma ruta, cuerpo y código, mediante una **tabla de rutas explícita** (no un comodín), de modo que una ruta desconocida reciba un `404` propio con la lista de grupos.
2. **Compone** cuatro endpoints (`/trabajos/{id}/completo`, `/proveedores/{id}/completo`, `/estado-del-sistema`, `POST /trabajos/asignacion`) llamando a los servicios **en paralelo** y degradando parcialmente (`DISPONIBLE` · `TODAVIA_NO_DISPONIBLE` · `NO_DISPONIBLE`).
3. **Crea y devuelve el identificador de correlación** (`X-Correlation-Id`) en todas sus respuestas, y lo manda hacia adentro.

El identificador se propaga por los cinco servicios existentes **sin tocar el dominio**: un `ContextVar` que se fija en el borde (petición HTTP o mensaje consumido) y que leen el despachador (propiedades), los mapeadores (envoltura, vía `correlacion.actual()`; `sobre()` no cambia) y el registro (`logging`). Ningún contrato de mensaje cambia y la clave de partición sigue siendo `trabajo_id`.

**Observabilidad por registro (FR-028, SC-007, CA-2.18).** Cada servicio —incluido Operaciones, que no publica nada— escribe el identificador en **todas** sus líneas de registro:

- `correlacion.instalar_registro()` instala un `logging.setLogRecordFactory` que agrega `correlation_id` a cada registro (así cubre todos los `logger`, propios y de bibliotecas, sin editar cada llamada).
- El formato de `logging.basicConfig` en cada `crear_app()` y en cada `consumidor.main()` pasa de `%(levelname)s %(name)s | %(message)s` a `%(levelname)s %(name)s | cid=%(correlation_id)s%(campos)s | %(message)s`. Fuera de una petición o mensaje (arranque, reintentos de suscripción) se escribe `cid=-`.
- El contexto se fija **por petición HTTP** (`before_request`/`teardown_request`) y **por mensaje consumido** (dentro de `correr()`, alrededor de `manejar(...)`, de modo que también cubre la línea de error de `negative_acknowledge`).
- El BFF escribe una línea por petición con el mismo formato (método, ruta, servicio destino, código, milisegundos, y `trabajo_id` cuando la ruta lo lleva).
- **`trabajo_id` en los registros (FR-028b).** La correlación sigue una petición; para seguir la vida de un trabajo entre peticiones, `correlacion.py` agrega un segundo contexto genérico de campos (`agregar_campos(**campos)`; no nombra ningún dominio: el nombre del campo lo pone quien llama) que la fábrica de registros escribe como ` trabajo_id=<id>` después de `cid=`. Se fija solo en el borde de cada servicio: rutas con `<id>` de trabajo (`campos_ruta` de `instalar_en_flask`), el `manejar_*` de los consumidores que reciben `trabajo_id`, y `_publicar` de Gestión de Trabajos (donde `POST /trabajos` genera el id dentro del comando). Los valores se validan con el mismo patrón que el identificador de correlación (evita inyección en registros); sin valor válido el campo no se escribe. No toca dominio ni contratos (FR-030). Las líneas emitidas antes de conocer el id no lo llevan.
- Se busca con `docker compose logs --no-color -t | grep <id>`; el orden lo da la marca de tiempo de Docker (detalle en `contracts/correlacion.md` y `quickstart.md`).

Llamadas HTTP y hilos con la biblioteca estándar (`urllib.request`, `concurrent.futures`); **cero dependencias nuevas**.

Hallazgos de la exploración que matizan la historia (detalle en [research.md](research.md); los dos principales):

- **CA-2.12 se verifica en el código, no en la red.** «Los servicios no se alcanzan entre sí» significa *no se llaman por HTTP; solo se comunican por eventos de Pulsar*. Compartir red no lo viola: hoy todos comparten `red-broker` y se resuelven por nombre (comprobado con Docker el 2026-09-19), y eso es aceptable. **La topología existente no se toca.** El BFF solo agrega una red por par BFF–servicio (`red-bff-<svc>`) como defensa adicional, y la verificación es estática: ningún servicio de dominio tiene cliente HTTP ni variable de entorno hacia otro servicio o hacia el BFF.
- **El puerto `8080` propuesto choca** con `broker-1` (`8080:8080`). El BFF publica en `8090` por defecto.

## Technical Context

**Language/Version**: Python 3.11 (`python:3.11-slim`, igual que los demás servicios)

**Primary Dependencies**: `Flask==3.0.3`, `gunicorn==22.0.0` (mismos pines que el resto), `pytest==8.2.0`. Biblioteca estándar: `urllib.request`, `concurrent.futures`, `contextvars`, `re`, `uuid`. El `requirements.txt` del BFF **no** incluye SQLAlchemy, psycopg2 ni pulsar-client (CA-2.3).

**Storage**: N/A — el BFF no guarda estado. En los servicios existentes **no** se agrega ninguna columna ni tabla (CA-2.21).

**Testing**: `pytest`. Las pruebas del BFF levantan **servidores HTTP reales** en puertos efímeros (`http.server.ThreadingHTTPServer`, biblioteca estándar) como servicios de atrás falsos, en lugar de simular `urlopen`, para ejercitar el camino real (Constitución VI). Verificación integral con `newman` (mismo criterio que `escenarios/mod-1.sh`: `newman` o `npx --yes newman`) y con scripts que reportan PASA/FALLA en `docs/resultados/`.

**Target Platform**: contenedor Linux bajo Docker Compose; sin cambios de código para AWS/Kubernetes (URLs por variables de entorno, FR-006).

**Project Type**: servicio web de borde (BFF) + cambio transversal acotado en los cinco servicios existentes (plantilla incluida).

**Performance Goals**: endpoints compuestos < 2 s en condiciones normales (SC-003), con llamadas en paralelo y tiempo límite propio por llamada; el reenvío agrega una sola llamada HTTP local por petición. «Condiciones normales» = p95 con 50 peticiones, concurrencia 5 y ningún servicio caído ni lento (FR-020). Con un servicio lento, `/proveedores/{id}/completo` (dos fases) puede llegar a 2 × `TIMEOUT_COMPUESTO_S` = 3 s; queda fuera de SC-003.

**Constraints**:
- Sin base de datos, sin broker, sin estado (FR-007/008); se puede escalar a N copias.
- Ningún servicio de dominio adquiere cliente HTTP ni variable de entorno hacia otro servicio o hacia el BFF (FR-022).
- La clave de partición y los contratos de mensajes no cambian (FR-031).
- El identificador de correlación no entra al dominio ni a tablas de negocio (FR-030).
- El BFF **no** depende de los servicios para arrancar: sin `depends_on` hacia ellos (si no, no podría degradar).

**Scale/Scope**: 17 rutas de reenvío + 4 compuestas + `/health` propio; 5 servicios de atrás; 5 copias del seedwork a modificar (plantilla + 4 servicios) más 1 copia idéntica dentro del BFF.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Veredicto | Evidencia / acción |
|---|---|---|
| **I. Comunicación solo por eventos** | ⚠️ **Excepción justificada** (ver Complexity Tracking) | El BFF hace HTTP hacia adentro y tiene variables de entorno que apuntan a los servicios. El principio nombra a los cuatro servicios de dominio y el BFF no es uno, pero la frase «ningún servicio MUST llamar a otro por HTTP» es general, así que la Gobernanza exige la excepción **por escrito en `docs/decisiones.md` con su alternativa descartada** (FR-039). Los servicios de dominio siguen sin poder hablarse. Se recomienda además enmendar el Principio I (MINOR) para nombrar «componente de borde». Además, las redes `red-bff-<svc>` hacen que cada API de dominio comparta red con el BFF, lo que excede la letra de «comparte red únicamente con el broker y con su propia base»; es una excepción del mismo tipo que la de HTTP (cada red contiene solo al BFF y a un servicio de dominio) y se registra también en Complexity Tracking y en `docs/decisiones.md`. |
| **II. Contratos con esquema** | ✅ Pasa, con una comprobación explícita | No se crea, renombra ni retipa ningún campo: `correlation_id` ya está en los cinco contratos como `String(default=None, required_default=True)`. Cambia el **valor**, no la forma. Como RS-4 exige `-v2` ante un «cambio de significado», se verificó que **ningún consumidor lee `correlation_id`** (solo se escribe; `grep` en `servicios/`, ver research R6), así que el cambio de valor no rompe a nadie. La decisión (cambio de valor sin `-v2`, con el costo de que el ciclo de vida de un trabajo ya no comparte un único identificador entre peticiones, mitigado por `trabajo_id` en los registros, FR-028b) queda escrita en `docs/decisiones.md` (T080-9); la saga de US-01 no debe usar `correlation_id` como clave del trabajo. `herramientas/verificar_contratos.py` se ejecuta igualmente. |
| **III. Capas separadas y servicios autónomos** | ✅ Pasa, con una desviación (ver Complexity Tracking) | `correlacion.py` es infraestructura del seedwork: no importa dominio, usa imports relativos, no nombra dominios ajenos, y es **byte-idéntico** en las 6 copias (lo comprueba `herramientas/verificar_aislamiento.py`, cumpliendo «un defecto corregido en una copia se corrige en todas»). `schema/v1/mensajes.py` **no** cambia y sigue byte-idéntico a `contratos/v1/mensajes.py` (criterio 8 del mismo script). El BFF **no** nace copiando la plantilla completa (arrastraría SQLAlchemy y Pulsar, contra CA-2.3): toma solo su esqueleto. Los campos de registro (`agregar_campos`) son genéricos: el módulo no nombra ningún dominio, y cada servicio pasa su propio nombre de campo (`trabajo_id`). |
| **IV. Comportamiento por datos, no por código** | ✅ Pasa | Direcciones de los servicios y tiempos límite salen de variables de entorno; el formato válido del identificador (`[A-Za-z0-9._:-]{1,64}`) es una constante de `correlacion.py`, no una variable, para que el archivo siga byte-idéntico en las seis copias; la tabla de rutas es un dato aislado en `rutas.py`. No se tocan reglas regionales ni el ciclo de vida. |
| **V. Resiliencia: al-menos-una-vez e idempotencia** | ✅ Pasa | Una reentrega lleva el mismo `correlation_id` (viaja en el mensaje). No cambian `negative_acknowledge`, la idempotencia, los productores únicos ni el `RLock`. La clave de partición sigue siendo `trabajo_id` (y `proveedor_id` en Acreditación); las propiedades siguen incluyendo `correlation_id`. |
| **VI. Verificación honesta** | ✅ Pasa (compromiso del plan) | Aserciones contra literales; servidores falsos reales; la cadena se verifica **releyendo** logs y mensajes del broker de una saga real; cada métrica PASA/FALLA en `docs/resultados/`; lo no ejecutable (saga sin US-01, AWS) se anota como **pendiente**. |
| **Restricciones técnicas y de despliegue** | ✅ Pasa | Python 3.11; el BFF arranca con `docker compose up -d --build` sin pasos manuales; variables con valor por defecto en `.env.example`; expone `/health`; sin secretos. |
| **Flujo y puertas de calidad** | ✅ Pasa (compromiso) | PR contra `main`; `pytest` del BFF y de los cinco servicios tocados; decisiones en `docs/decisiones.md`; el cambio de correlación toca la ruta de publicación y el bucle de consumo de todos los servicios, así que **afecta escenarios de calidad**: se ejecutan `escenario-6.sh`, `escenario-8.sh`, `mod-1/2/3.sh` y `esquemas.py` o se anotan como pendientes. |

**Resultado del gate**: PASA con **tres desviaciones justificadas** (Complexity Tracking; la tercera, las redes `red-bff-<svc>`, se agregó tras `/speckit-analyze`). Post-diseño (Fase 1) se re-evaluó: sin cambios (ver nota al final de research.md).

## Project Structure

### Documentation (this feature)

```text
specs/001-bff-entry-point/
├── plan.md              # Este archivo
├── research.md          # Fase 0: decisiones y hallazgos
├── data-model.md        # Fase 1: modelos en memoria (el BFF no persiste nada)
├── quickstart.md        # Fase 1: cómo levantar y verificar de punta a punta
├── contracts/
│   ├── bff-api.md       # Rutas, respuestas compuestas y errores propios del BFF
│   └── correlacion.md   # Contrato del identificador: cabecera, sobre, propiedades, registro
├── checklists/
│   └── requirements.md  # (de /speckit-specify)
└── tasks.md             # Fase 2 (/speckit-tasks — NO lo crea este comando)
```

### Source Code (repository root)

```text
servicios/bff/                          # NUEVO — componente de borde
├── Dockerfile                          # python:3.11-slim + gunicorn gthread
├── README.md                           # FR-038: rutas, compuestos, cómo seguir una petición
├── pytest.ini
├── requirements.txt                    # Flask, gunicorn, pytest — nada más
├── src/bff/
│   ├── __init__.py                     # crear_app(): ganchos de correlación, manejadores de error
│   ├── config.py                       # URLs de los servicios, tiempos límite (variables de entorno)
│   ├── correlacion.py                  # copia byte-idéntica del módulo de los servicios
│   ├── rutas.py                        # tabla de rutas de reenvío (datos): método, patrón, servicio
│   ├── cliente.py                      # cliente HTTP (urllib) + clasificación de fallos
│   ├── reenvio.py                      # vista genérica de reenvío fiel
│   ├── compuestos.py                   # los 4 endpoints compuestos (paralelo + degradación)
│   ├── errores.py                      # 404/405/500 y 503/502 propios, siempre JSON
│   └── salud.py                        # GET /health del propio BFF
└── tests/
    ├── conftest.py                     # servicios de atrás falsos (ThreadingHTTPServer)
    ├── test_reenvio.py                 # CA-2.5, 2.7 — fidelidad de código/cuerpo/consulta
    ├── test_compuestos.py              # CA-2.8…2.11 — composición y degradación
    ├── test_fallos.py                  # CA-2.14, 2.15 — 503, aislamiento entre rutas, sin trazas
    ├── test_correlacion.py             # CA-2.16, 2.17, 2.17b — crear/respetar/devolver
    └── test_sin_estado_ni_broker.py    # CA-2.3 — sin dependencias de BD ni Pulsar

servicios/{_plantilla,gestion_trabajos,operaciones,acreditacion,emparejamiento}/   # CAMBIO TRANSVERSAL
└── src/<paquete>/
    ├── seedwork/infraestructura/correlacion.py      # NUEVO (idéntico en las 5 copias)
    ├── __init__.py                                  # formato de log con cid + ganchos HTTP
    ├── consumidor.py | seedwork/infraestructura/consumidores.py   # `correr()`: fija el contexto por mensaje
    ├── seedwork/infraestructura/despachadores.py    # propiedad correlation_id desde el contexto (donde publica)
    ├── seedwork/infraestructura/schema/v1/mensajes.py  # SIN CAMBIOS: sigue idéntico a `contratos/v1/mensajes.py`; los mapeadores pasan `correlacion.actual()`
    └── modulos/*/{aplicacion/handlers.py, infraestructura/mapeadores.py, infraestructura/consumidores.py}  # los mapeadores pasan `correlacion.actual()` y se elimina el id de dominio como correlación (GT, ACR, EMP); `trabajo_id` al contexto de registro (`consumidores.py` y `_publicar`: GT, OPS, EMP)
tests/  # cada servicio: pruebas del módulo, del gancho HTTP y del camino de publicación

docker-compose.yml                       # servicio `bff` + redes red-bff-<svc> (una por par); NO se tocan las redes existentes; sin depends_on
.env.example                             # PUERTO_BFF=8090
infra/aws/terraform/main.tf              # regla de entrada para el puerto del BFF + salida de salud
herramientas/verificar_aislamiento.py    # NUEVO — comprobaciones estáticas (CA-2.3, 2.12, 2.13, 2.21, copias idénticas de `correlacion.py` y de `mensajes.py` frente a `contratos/`); lee `docker compose config`
escenarios/bff.sh                        # NUEVO — cadena de correlación, particiones, 503 (CA-2.17c…2.22)
postman/hogar-alpes-bff.postman_collection.json          # NUEVO — 10 carpetas
postman/bff-local.postman_environment.json               # NUEVO
postman/bff-aws.postman_environment.json                 # NUEVO
README.md · docs/decisiones.md · docs/actividades.md · docs/hoja-verificacion-infraestructura.md   # docs
```

**Structure Decision**: un servicio nuevo plano (`servicios/bff/`) porque no tiene capas de dominio ni de persistencia que separar; la separación que sí existe (`cliente` = infraestructura, `rutas` = datos, `compuestos`/`reenvio` = aplicación) se refleja en módulos distintos. El cambio de correlación **no** crea un módulo compartido entre servicios (decisión TO-7): es una copia idéntica por servicio, verificada por script.

**Orden de construcción** (dependencias reales entre historias):

1. **Regla de correlación en la plantilla primero** — `saga_log` (US-01) nace copiando la plantilla; si la plantilla ya trae `correlacion.py`, hereda el comportamiento sin trabajo extra.
2. Correlación en los cuatro servicios + pruebas.
3. BFF: reenvío → compuestos → correlación propia.
4. `docker-compose.yml` (servicio `bff` y redes `red-bff-<svc>`); `verificar_aislamiento.py`.
5. Colección de Postman; `escenarios/bff.sh`; documentación.
6. **Segunda pasada cuando exista `saga_log`**: sin él, `/sagas/*` responde `503` nombrando `saga-log`, la parte `saga` de `/trabajos/{id}/completo` sale `NO_DISPONIBLE`, y las carpetas 5 y 7 de Postman quedan **pendientes** (CA-2.25 y CA-2.26 no pueden cerrarse antes de US-01).

## Complexity Tracking

| Desviación | Por qué es necesaria | Alternativa más simple descartada y por qué |
|---|---|---|
| **El BFF hace HTTP hacia los servicios** (excepción al Principio I) | Es su razón de ser: un punto de entrada único y consultas compuestas exigen llamadas síncronas hacia adentro. El propio código lo evitó antes: `GET /trabajos/{id}/seguimiento` se **retiró** de Gestión de Trabajos porque habría sido una llamada GT→OPS (`gestion_trabajos/__init__.py`, GT-5). El BFF es la puerta de entrada de los clientes, no un servicio de dominio. | (a) *Que el BFF lea de una proyección alimentada por eventos*: obliga a darle base de datos y consumidor —justo lo que la historia prohíbe— y duplica la lógica de todos los servicios. (b) *No hacer compuestos*: es un simple gateway y no cumple D5-4. |
| **El BFF no nace copiando toda la plantilla** (Principio III) | La plantilla trae seedwork de dominio, SQLAlchemy, Pulsar y un proceso consumidor; el BFF no puede tener nada de eso (CA-2.3, FR-008). | *Copiar y podar*: deja rastros (dependencias, carpetas vacías, variables) que CA-2.3 tendría que descartar a mano; es más frágil que partir del esqueleto (`Dockerfile`, fábrica, `/health`, `pytest.ini`). |
| **Cada API de dominio se une a una red `red-bff-<svc>` compartida con el BFF** (excepción a la cláusula de redes del Principio I: «cada servicio comparte red únicamente con el broker y con su propia base») | El BFF necesita alcanzar la API de cada servicio; una red por par (BFF + un solo servicio) evita que el BFF comparta red con el broker o con las bases (FR-021). No cambia ninguna red existente. | (a) *Poner al BFF en `red-broker`*: rompe FR-021 y lo acerca al broker y a todos los servicios. (b) *Sin redes por par*: el BFF no tendría ruta a los servicios. Se resuelve del todo enmendando el Principio I (MINOR) para nombrar «componente de borde». |
