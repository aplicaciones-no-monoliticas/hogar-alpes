# Research — BFF y trazabilidad por petición

**Feature**: `001-bff-entry-point` · **Fecha**: 2026-09-19

No quedaron `NEEDS CLARIFICATION` abiertos en el Technical Context. Esta investigación resuelve las decisiones de diseño que la spec dejó para la planificación (tiempos límite, límites del identificador, cómo propagarlo sin tocar el dominio) y **registra los hallazgos del código que contradicen o matizan la historia**. Los hallazgos van primero porque cambian el alcance.

Convención: **Decisión · Justificación · Alternativas descartadas**. Lo verificado en esta sesión lleva su evidencia; lo que **no** se pudo ejecutar se marca *pendiente*.

---

## Hallazgos que matizan la historia US-02

| # | Hallazgo | Evidencia | Consecuencia en el plan |
|---|---|---|---|
| H1 | **La comprobación de red de CA-2.12 («el nombre de otro servicio no resuelve») no aplica**: los servicios comparten `red-broker` y sí se resuelven, y es aceptable, porque la regla del proyecto es *no comunicarse de forma síncrona*, no aislar la red (aclaración del equipo, 2026-09-19) | `docker compose config` (2026-09-19): las API y los consumidores de los cuatro servicios están en `red-broker`. Experimento con Docker: dos contenedores en una red común se resuelven (`getent hosts` → `exit=0`). `docs/decisiones.md:314` ya lo admitía; `docs/hoja-verificacion-infraestructura.md:226` presenta el aislamiento entre APIs como un hecho de red («falla: no comparten red»), lo cual **no es cierto**: lo garantiza el código y el uso exclusivo de Pulsar. Línea base verificada: `grep` de `urllib`, `requests`, `httpx`, `http.client`, `aiohttp` y `http://` en `servicios/**/src` → **0 coincidencias** | R7: la verificación es estática y la topología no cambia |
| H2 | **El puerto `8080` propuesto ya está ocupado** en el host por `broker-1` (`"8080:8080"`; `broker-2` usa `8081`) | `docker-compose.yml:106,144` | El BFF publica en `${PUERTO_BFF:-8090}` |
| H3 | **`GET /acreditaciones/{id}` busca por el id de la acreditación, no por `proveedor_id`**; en los datos reales son UUID distintos | `obtener_acreditacion.py`, `cargar_acreditaciones.py:111-112` | En `/proveedores/{id}/completo`, `{id}` es el **id de la acreditación** (el que devuelve `POST /acreditaciones`); la respuesta incluye `proveedor_id` |
| H4 | **La colección de la Entrega 4 no es «solo cambiar la dirección» para su primera petición**: `GET /health` afirma `service == 'gestion-trabajos'` | `hogar-alpes.postman_collection.json`, carpeta «0 · Salud del servicio» | El `/health` del BFF es el **propio** (necesario para balanceadores y Kubernetes). CA-2.6 se cumple para todas las carpetas **excepto** esa petición, que se documenta como excepción y se excluye con `--folder` |
| H5 | **Tensión FR-003 ↔ FR-026**: el reenvío debe devolver «el mismo cuerpo», pero `POST /trabajos` debe llevar además el identificador de correlación en el cuerpo | Spec | R3: se **agrega** un campo solo en respuestas `2xx` de las dos rutas que inician saga; los errores no se tocan. La colección de la Entrega 4 solo afirma campos sueltos (`cuerpo.id`, `cuerpo.estado`), no igualdad profunda, así que sigue en verde |
| H6 | **La colección de la Entrega 4 solo cubre Trabajos y Operaciones** (`baseUrl`, `baseUrlOps`) | Estructura de la colección | CA-2.6 no prueba la fidelidad del reenvío de Acreditación ni Emparejamiento; la prueban `tests/test_reenvio.py` y las carpetas 2 y 3 de la colección nueva |
| H7 | **El id de correlación se escribe en dos lugares distintos** y ambos usan ids de dominio hoy | Envoltura: `sobre()` en `mensajes.py` (Emparejamiento, Acreditación, plantilla) y `_sobre()` propio en `gestion_trabajos/.../mapeadores.py:104`. Propiedades: `handlers.py` de los tres servicios que publican. Acreditación usa `proveedor_id` | R6: los dos lugares leen del mismo contexto |
| H8 | **Los consumidores no leen `correlation_id`** (solo se escribe) | `grep correlation_id servicios/`: todas las coincidencias son de escritura o de definición de contrato | R6 y Constitución II: el cambio de valor no rompe ningún consumidor, no exige `-v2` |
| H9 | **Existen cuatro bucles `correr()` distintos** (uno por servicio consumidor) | `acreditacion/consumidor.py:26`, `emparejamiento/consumidor.py:26`, `operaciones/consumidor.py:26`, `gestion_trabajos/seedwork/infraestructura/consumidores.py:27` | La propagación por mensaje se agrega en las 4 copias (+ plantilla), no en un solo lugar |
| H10 | **No se pudo verificar en esta sesión** contra el sistema real: cadena de logs, mensajes del broker, `newman`, escenarios | El experimento de red sí se ejecutó; el resto depende de implementar | *Pendiente* hasta la implementación; se anotará como pendiente si no se corre |

---

## R1 · Cliente HTTP y concurrencia

**Decisión**: `urllib.request` (con un *opener* sin seguimiento de redirecciones) y `concurrent.futures.ThreadPoolExecutor` para las llamadas en paralelo de los compuestos. gunicorn con `--worker-class gthread --threads ${THREADS:-8} -w ${WORKERS:-2}`.

**Justificación**: CA-2.2 pide biblioteca estándar «igual que `herramientas/medir_latencia.py`». `gthread` es un tipo de worker **incluido en gunicorn**, no una dependencia nueva, y evita que un servicio de atrás lento deje sin atender `/health` con el worker síncrono por defecto. El *opener* sin redirecciones garantiza que un `308` de un servicio llegue tal cual al cliente (fidelidad).

**Alternativas descartadas**: `requests`/`httpx` (dependencia nueva, prohibida por CA-2.2); `asyncio` con `aiohttp` (framework nuevo); un worker síncrono (un solo servicio lento bloquearía todo el BFF).

## R2 · Enrutamiento: tabla explícita, no comodín

**Decisión**: `rutas.py` declara las 17 rutas como datos (`método`, `patrón`, `servicio`) y `__init__.py` registra una vista genérica por ruta con `add_url_rule`. Lo que no esté en la tabla cae en el manejador `404` del BFF, que responde con la lista de grupos (FR-005).

**Justificación**: un comodín por prefijo no distingue «ruta que no existe» (404 propio con grupos) de «recurso que no existe» (404 del servicio, que debe pasar sin cambios). Con la tabla, el 404 de un servicio siempre es del servicio. También hace explícita la lista que R5-10 teme que se desactualice, y permite una prueba que la compare con las rutas reales de cada servicio.

**Alternativas descartadas**: comodín `/<path:p>` por grupo (404 ambiguo); generar la tabla leyendo los servicios en caliente (crea acoplamiento en tiempo de ejecución).

## R3 · Fidelidad del reenvío

**Decisión**: se reenvían método, ruta, cadena de consulta **tal cual**, cuerpo en bytes y `Content-Type`/`Accept`. Se devuelven código, cuerpo en bytes y `Content-Type` del servicio. Se descartan cabeceras de salto (`Connection`, `Transfer-Encoding`, `Keep-Alive`). `HTTPError` de `urllib` (4xx) se lee y se devuelve como respuesta, no como excepción.

**Excepción acotada (H5)**: en `POST /trabajos` y `POST /trabajos/asignacion`, si el servicio responde `2xx` con un objeto JSON, el BFF **agrega** `correlation_id` (y en `asignacion`, además, las direcciones de seguimiento). Nunca elimina ni cambia campos existentes, y nunca toca respuestas de error.

**Justificación**: CA-2.17b obliga a poner el identificador en el cuerpo; CA-2.5/2.7 obligan a no alterar lo demás. Un campo aditivo cumple ambas y las aserciones de la colección de la Entrega 4 lo toleran.

**Alternativas descartadas**: no agregar el campo (incumple CA-2.17b); envolver la respuesta en `{"data": …}` (rompe la fidelidad).

## R4 · Modelo de fallos

**Decisión** (tabla completa en `contracts/bff-api.md`):

| Situación del servicio de atrás | Respuesta del BFF |
|---|---|
| Responde `2xx`/`3xx`/`4xx` | Se devuelve tal cual |
| No resuelve el nombre, rechaza la conexión, agota el tiempo límite | `503` JSON que **nombra el servicio** y el motivo |
| Responde `5xx` | `502` JSON que nombra el servicio y el código recibido; **no se reenvía el cuerpo** del servicio |
| Error no previsto dentro del BFF | `500` JSON genérico («Error interno del BFF») con el identificador; la traza va **solo al registro**, nunca al cliente |
| Ruta o método inexistente | `404`/`405` JSON con la lista de grupos / métodos permitidos |

Todas llevan `X-Correlation-Id` (gancho `after_request`, que también cubre los manejadores de error).

**Justificación**: FR-010/FR-012 piden `503` con el servicio nombrado y prohíben trazas y `500` sin explicación. La spec no cubre el caso «el servicio responde 5xx»; se decidió `502` (*Bad Gateway* describe exactamente «respondió mal») en lugar de reenviar un cuerpo que podría ser una página HTML o una traza.

**Alternativas descartadas**: reenviar el `5xx` tal cual (puede filtrar trazas, contra CA-2.15); convertirlo en `503` (mezcla «no responde» con «responde con error», que se diagnostican distinto).

**Tiempos límite**: `TIMEOUT_REENVIO_S=5` para reenvío directo y `TIMEOUT_COMPUESTO_S=1.5` por llamada en los compuestos, ambos por variable de entorno. Con llamadas en paralelo y `1.5 s`, un compuesto con un servicio colgado tarda ≈ `1.5 s` (< 2 s de SC-003 incluso degradado); `/proveedores/{id}/completo` tiene una dependencia en dos fases (R5) y su peor caso degradado es ≈ `3 s`, aceptable porque SC-003 habla de «condiciones normales».

## R5 · Endpoints compuestos: partes y degradación

**Decisión**: cada parte lleva un estado — `DISPONIBLE`, `TODAVIA_NO_DISPONIBLE` (el servicio respondió `404` para una parte **derivada**: seguimiento, emparejamiento o saga de un trabajo recién creado) o `NO_DISPONIBLE` (no responde, agotó el tiempo o dio `5xx`). Reglas de la respuesta:

1. La parte **raíz** (`trabajo`, `acreditacion`) con `404` → el BFF devuelve **ese `404` tal cual** (el recurso no existe; no se disfraza, spec «Edge Cases»).
2. Si **todas** las partes son `NO_DISPONIBLE` → `503` que nombra los servicios.
3. En cualquier otro caso → `200` con las partes y sus estados.

`GET /proveedores/{id}/completo` tiene **dos fases**: primero acreditación e historial en paralelo; luego, con `pais`/`ciudad`/`categorias` de la acreditación, una consulta a `/candidatos` **por categoría** en paralelo, y `candidato.aparece = true` si el `proveedor_id` figura en alguna. Si la acreditación no está disponible, `candidato` es `NO_DISPONIBLE` con motivo `DEPENDE_DE_ACREDITACION`. `{id}` es el id de la acreditación (H3).

`GET /estado-del-sistema` consulta `/health` de los cinco servicios y `/sagas/resumen` en paralelo, agrega el propio BFF como sexto componente, y responde `200` con `estado_general` `OK`/`DEGRADADO` **incluso si todos están caídos** (una vista de estado debe ser legible justo cuando el sistema está mal; esta es la única excepción a la regla 2).

`POST /trabajos/asignacion` reenvía el cuerpo a `POST /trabajos` y, si responde `202`, agrega `correlation_id`, `seguimiento_saga` (`/sagas/{id}`) y `seguimiento_completo` (`/trabajos/{id}/completo`). Errores: sin cambios.

**Limitación aceptada**: si el servicio de Trabajos está caído y el trabajo no existe, las partes derivadas también responden `404` y salen `TODAVIA_NO_DISPONIBLE`; el BFF no puede distinguir «aún no propagado» de «nunca existió» sin la parte raíz. La respuesta sigue siendo honesta (`trabajo: NO_DISPONIBLE`).

**Alternativas descartadas**: un cuarto estado `NO_VERIFICABLE` (complejidad sin pedido de la spec); consultar `/candidatos` solo por la primera categoría (respuesta incorrecta para proveedores multicategoría).

## R6 · Identificador de correlación sin tocar el dominio (FR-027…FR-030)

**Decisión**: módulo `seedwork/infraestructura/correlacion.py`, **idéntico byte a byte** en plantilla + 4 servicios + BFF:

- `ContextVar` con el identificador vigente.
- `normalizar(valor)`: válido si cumple `^[A-Za-z0-9._:-]{1,64}$`; si no, `None` (se trata como ausente). Cubre vacío, demasiado largo y caracteres que alteren líneas de registro (saltos de línea, espacios, `|`, `=`).
- `actual()`: **get-or-create** — si no hay valor, crea un `uuid4` y lo deja fijado. Es lo que hace que la envoltura y las propiedades **coincidan siempre** y que FR-029 se cumpla por construcción («quien lo recibe, lo crea»).
- `contexto(valor)`: administrador de contexto que fija `normalizar(valor) or nuevo` y lo restaura al salir.
- `instalar_registro()`: `logging.setLogRecordFactory` que agrega `correlation_id` a cada registro (`-` si no hay contexto).
- `instalar_en_flask(app)`: `before_request` (lee `X-Correlation-Id`, normaliza o crea, fija), `after_request` (lo devuelve en la respuesta), `teardown_request` (limpia).

Puntos de contacto, todos en el **borde**:

| Borde | Cambio |
|---|---|
| Petición HTTP entrante | `instalar_en_flask` en `crear_app()` |
| Mensaje consumido | `correr()`: `with correlacion.contexto(getattr(valor, 'correlation_id', None) or propiedad):` alrededor de `manejar(...)`. Precedencia: campo del sobre → propiedad `correlation_id` → crear |
| Mensaje publicado | `Despachador._publicar_mensaje`: `properties['correlation_id'] = correlacion.actual()` (pisa lo que pase el handler); los mapeadores de los tres servicios que publican pasan `correlation_id=correlacion.actual()` a `sobre()` (y `_sobre()` en Gestión de Trabajos); `sobre()` **no cambia** y sigue idéntico a `contratos/v1/mensajes.py` |
| Registro | `instalar_registro()` + nuevo formato con `cid=` |

En los handlers y mapeadores se **elimina** la correlación derivada del dominio (`trabajo_id`, `proveedor_id`); ningún comando, evento de dominio ni tabla gana un campo (FR-030).

**Por qué funciona sin pasar el id por el dominio**: la Unidad de Trabajo despacha los eventos de integración **de forma síncrona en el mismo hilo** (`uow.py`, `dispatcher.send` dentro de `commit()`), así que el contexto fijado al entrar la petición o el mensaje sigue vigente cuando el `Despachador` publica. Los hilos de Emparejamiento (regional y proyección) son distintos, pero cada uno fija su propio contexto por mensaje.

**Justificación de `-v2`**: RS-4 exige un stream nuevo ante «cambio de significado». No aplica: el campo conserva su tipo y su función («correlacionar», `TO-4`), y H8 muestra que nadie depende de que valga el id del trabajo.

**Generador de carga**: `herramientas/generador_carga.py` publica con `correlation_id = trabajo_id` (un valor válido); se propaga tal cual y **no se modifica**. FR-029/CA-2.22 (mensaje **sin** identificador) se verifica en `escenarios/bff.sh` publicando un mensaje con el campo vacío por el camino real.

**Alternativas descartadas**:

| Alternativa | Por qué no |
|---|---|
| Agregar `correlation_id` a comandos y eventos de dominio | Contamina el dominio (FR-030, R5-10c) |
| `flask.g` | No existe en los consumidores |
| Variable global | Se cruzaría entre hilos/peticiones concurrentes |
| Interceptores del cliente de Pulsar | No se evaluó si `pulsar-client` 3.5 para Python los soporta (*sin verificar*); aun así el `Despachador` ya es el único punto de publicación, así que no aportan nada que ese punto no cubra |
| Módulo compartido entre servicios | Contra TO-7 (seedwork duplicado a propósito); se mitiga con verificación de copias idénticas |
| Cambiar la clave de partición | Prohibido por FR-031; el despachador ya recibe `clave` y `propiedades` como argumentos separados |

**Registro (observabilidad)**: formato `%(levelname)s %(name)s | cid=%(correlation_id)s | %(message)s`. Se usa `setLogRecordFactory` (y no un `Filter` en un `Handler`) porque cubre **todos** los registros del proceso, incluidos los de bibliotecas y los de hilos que se crean después. Orden: `docker compose logs --no-color -t | grep -F <id> | sort -t'|' -k2` (las marcas ISO-8601 de Docker ordenan lexicográficamente). Límite conocido: el orden entre contenedores depende de que compartan reloj (mismo host en Compose; en Kubernetes conviene un agregador que ordene por tiempo).

## R7 · Aislamiento entre servicios y redes (H1) — **decidido: la topología existente no cambia**

**Aclaración del equipo (2026-09-19):** «los servicios de dominio no se alcanzan entre sí» significa **no comunicarse de forma síncrona** —sin HTTP entre ellos— y comunicarse solo por eventos de Pulsar. Compartir una red Docker es aceptable y no se restringe.

**Qué se comprobó** (2026-09-19; `docker compose config` y contenedores `alpine:3.20` desechables, ya eliminados):

| Comprobación | Resultado |
|---|---|
| Las API y consumidores de los cuatro servicios están en `red-broker` | Sí (`docker compose config`) |
| Dos contenedores en una red común se resuelven por nombre | Sí (`getent hosts` → `exit=0`) |
| Un contenedor que solo está en redes propias `bff-a`/`bff-b` resuelve a los servicios de esos pares | Sí |
| Ese mismo contenedor resuelve al broker, que está en otras redes | **No** (`exit=2`) |

Conclusión: la resolución de nombres **no** sirve para demostrar la regla del proyecto (ya hoy los servicios se resuelven), y por eso no es el criterio de CA-2.12. Sí sirve para garantizar que el BFF no toque el broker ni las bases de datos.

**Decisión:**

- **No se modifica ninguna red existente** (`red-broker`, `red-<svc>` de las bases de datos).
- El BFF se une **solo** a redes propias `red-bff-<svc>` (una por par: `red-bff-trabajos`, `red-bff-operaciones`, `red-bff-acreditacion`, `red-bff-emparejamiento`, `red-bff-saga`); cada servicio de dominio se une, además de a las suyas, a su `red-bff-<svc>`. Cada una contiene **exactamente** al BFF y a un servicio.
- El BFF no está en `red-broker` ni en ninguna red de base de datos, así que **no resuelve** el broker ni las bases (CA-2.3).
- Las redes por par son **defensa adicional** (el BFF no sirve de puente de red entre servicios), no el criterio de CA-2.12. Si el equipo prefiere simplificar, una sola red `red-bff` con el BFF y los cinco servicios es equivalente para la regla; se mantiene por par porque es lo que propone la historia (R5-7) y cuesta cinco líneas de Compose.

**Verificación de CA-2.12 (estática)** — `herramientas/verificar_aislamiento.py`, sobre código y `docker compose config`, solo lectura:

1. Ningún servicio de dominio importa ni usa un cliente HTTP (`urllib`, `requests`, `httpx`, `http.client`, `aiohttp`) ni contiene literales `http://`. **Línea base ya verificada: 0 coincidencias hoy** en `servicios/**/src`.
2. Ninguna variable de entorno de un servicio de dominio en `docker-compose.yml` apunta al nombre de otro servicio de dominio ni al BFF; solo el BFF tiene variables `URL_*` (FR-022, CA-2.13).
3. Cada red `red-bff-*` tiene exactamente dos miembros: el BFF y un servicio de dominio; el BFF no pertenece a ninguna otra red.
4. El BFF no declara volúmenes de datos, `DATABASE_URI` ni `BROKER_HOST`, y su `requirements.txt` no incluye `pulsar-client`, `SQLAlchemy` ni `psycopg2` (CA-2.3).
5. Ningún servicio de dominio llama al BFF: ninguna variable ni literal con el nombre `bff`.

**Lo que este criterio no comprueba, a propósito:** que los servicios no puedan alcanzarse a nivel de red. No es un objetivo del proyecto. La comprobación de red que ya existía (`getent hosts postgres-<otro>`, 9 de 9) sigue vigente y solo aplica a las **bases de datos**, donde el aislamiento sí es de red.

**Documentación a corregir:** `docs/hoja-verificacion-infraestructura.md` §6 (líneas ≈ 224-226) muestra un `urlopen('http://operaciones:5000/health')` desde `gestion-trabajos` con el comentario «falla: no comparten red». Es incorrecto —comparten `red-broker`—; debe decir que la regla la garantiza el código y el uso exclusivo de Pulsar, y ofrecer como comprobación `verificar_aislamiento.py`. No se ejecutó esa llamada; es una afirmación por la topología de `docker-compose.yml`, *sin verificar* contra el sistema levantado.

**Impacto en los escenarios de la Entrega 4:** como la topología no cambia, ya no hay riesgo por redes. Se siguen ejecutando `escenario-6.sh`, `escenario-8.sh` y `mod-1/2/3.sh` porque el cambio de correlación sí toca la publicación y el consumo de todos los servicios (R6).

## R8 · Puerto, despliegue y configuración

**Decisión**: puerto interno `5000` (igual que los demás), publicado como `${PUERTO_BFF:-8090}` (H2). Variables: `URL_TRABAJOS`, `URL_OPERACIONES`, `URL_ACREDITACION`, `URL_EMPAREJAMIENTO`, `URL_SAGAS` (por defecto `http://<servicio>:5000`, que funciona en Compose y en Kubernetes con nombres de Service iguales), `TIMEOUT_REENVIO_S`, `TIMEOUT_COMPUESTO_S`, `WORKERS`, `THREADS`, `LOG_LEVEL`. **Sin `depends_on`** hacia los servicios (si no, no arrancaría con uno caído ni con `saga-log` aún inexistente). AWS: nueva regla de entrada en `infra/aws/terraform/main.tf` (hoy abre `8000-8003`) y salida de salud del BFF.

**Alternativas descartadas**: `8080` (ocupado); `8005` (se confunde con la serie de servicios de dominio, y `8004` es para `saga-log`); no publicar puerto (el cliente no lo alcanzaría).

## R9 · Dependencia con US-01 (`saga_log` aún no existe)

**Decisión**: el BFF trae las tres rutas `/sagas/*` desde el primer día, apuntando a `URL_SAGAS` (`http://saga-log:5000`). Mientras el servicio no exista, el nombre no resuelve → `503` nombrando `saga-log`; la parte `saga` de los compuestos es `NO_DISPONIBLE` y `estado-del-sistema` lo marca `DOWN`. La red `red-bff-saga` se declara ya; `saga-log` se unirá a ella al crearse.

**Consecuencia registrada**: las carpetas 5 y 7 de Postman y `CA-2.25`/`CA-2.26` quedan **pendientes** hasta que US-01 exista; `escenarios/bff.sh` los reporta como *pendiente*, no como PASA. Nota para US-01: el servicio nuevo debe nacer de la plantilla **ya actualizada** (R6) y unirse a `red-broker`, a su propia red de base de datos (`red-saga`) y a `red-bff-saga`.

## R10 · Estrategia de pruebas

| Nivel | Qué | Cómo (literales, camino real) |
|---|---|---|
| Unitario BFF | Reenvío, composición, fallos, correlación, sin BD/Pulsar | Servidores falsos reales en puertos efímeros; se afirma contra códigos y cuerpos literales, no contra lo que el propio BFF acaba de producir. `test_sin_estado_ni_broker.py` lee `requirements.txt` y el `Dockerfile` |
| Unitario servicios | Módulo `correlacion`, gancho HTTP, envoltura y propiedades, clave de partición | `Despachador._publicar_mensaje` con `productor` simulado que captura `send(...)`; se afirma `partition_key == '<trabajo_id literal>'` y `properties['correlation_id'] == '<id literal>'`. El `conftest.py` actual anula `publicar_evento`, por eso la prueba baja un nivel |
| Estático | CA-2.12/2.13 (sin cliente HTTP ni variables hacia otro servicio o el BFF; redes `red-bff-*` con solo BFF + un servicio); sin `correlation` en dominio ni tablas; BFF sin BD/Pulsar/volúmenes; 6 copias idénticas de `correlacion.py` | `herramientas/verificar_aislamiento.py` (solo lectura) |
| Integración (Docker) | Cadena de una saga real en los logs; propiedades y envoltura en un mensaje real; partición; mensaje sin id; `503` con un servicio detenido | `escenarios/bff.sh` → PASA/FALLA en `docs/resultados/` |
| Regresión | Colección de la Entrega 4 contra el BFF; `pytest` de los cuatro servicios; escenarios 6, 8, mod-1/2/3; `verificar_contratos.py` | `newman ... --folder` (todas menos «0 · Salud del servicio», H4) |
| Colección BFF | 10 carpetas, ≥ 1 aserción por petición | `newman` con `bff-local` |

## R11 · Postman

**Decisión**: `bff-local` y `bff-aws` definen `bffUrl` y **también** `baseUrl` y `baseUrlOps` apuntando al BFF, de modo que **las dos colecciones corran con el mismo entorno**. Las carpetas 5 y 7 (sagas) se marcan pendientes hasta US-01. La carpeta 8 detiene un servicio con Docker, por lo que la ejecuta `escenarios/bff.sh`, no `newman` solo (`newman` no controla contenedores); en Postman queda su versión «sin servicio caído».

## R12 · Documentación y decisiones a anotar

`docs/decisiones.md` (FR-039), con su verificación ejecutada: (1) el BFF como componente de borde y la excepción al Principio I; (2) «no alcanzarse entre sí» = sin comunicación síncrona (no aislamiento de red), redes `red-bff-<svc>` como defensa adicional, y la corrección de `hoja-verificacion-infraestructura.md` §6; (3) correlación por contexto de borde y por qué no por dominio; (4) `502` para `5xx` de los servicios; (5) puerto `8090`; (6) `{id}` de `/proveedores/{id}/completo`; (7) excepción del `/health` en CA-2.6. `docs/actividades.md` (quién, commits, PR). Se recomienda proponer la enmienda del Principio I (MINOR) por PR aparte.

---

## Re-evaluación de la Constitución tras el diseño (Fase 1)

Sin cambios respecto al gate inicial: el diseño no agrega dependencias, no toca contratos ni la clave de partición, y las desviaciones son tres (Principio I por HTTP, Principio I por las redes `red-bff-<svc>` —agregada tras `/speckit-analyze`— y plantilla). Nueva verificación derivada del diseño: **`correlacion.py` byte-idéntico en 6 copias** (Principio III) queda automatizada en `verificar_aislamiento.py`.
