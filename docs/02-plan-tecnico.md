# Entrega 4 · Plan técnico — Fase 2 `/plan`

| Proyecto | Estado | Base | Entrega | Equipo |
|---|---|---|---|---|
| Hogar de los Alpes | **Borrador para aprobación** | `01-especificacion.md` (aprobada) | **2026-09-13** | Stiven Cardona · Juan Manuel Domínguez · Andrés Gómez |

Abreviaturas: **GT** `gestion_trabajos` · **OPS** `operaciones` · **EMP** `emparejamiento` · **ACR** `acreditacion`. Los `CA-*`, `RNF-*`, `RS-*` y `G-*` remiten a la especificación.

---

## 0. La restricción que manda: dos días

La especificación está aprobada el 11 y la entrega es el 13. El plan está dimensionado para eso:

- **Lo mínimo por servicio**: una o dos tablas, los comandos y consultas que piden los escenarios, nada más.
- **Mediciones con scripts simples** (bash + Python), sin herramientas nuevas que instalar.
- **Líneas de corte explícitas** (§10): qué se sacrifica primero si el tiempo no alcanza, y qué no se toca nunca.
- **Un spike de 45 minutos al principio** (§2.5) para despejar el único riesgo técnico que podría tumbar la demostración de esquemas.

---

## 1. Estructura del repositorio

```
hogar-alpes/
├── servicios/
│   ├── gestion_trabajos/     Dockerfile · requirements.txt · src/gestion_trabajos · tests/
│   ├── operaciones/          ídem · src/operaciones
│   ├── emparejamiento/       ídem · src/emparejamiento
│   └── acreditacion/         ídem · src/acreditacion
├── infra/
│   ├── pulsar/               inicializar.sh · agregar-region.sh · politicas.env
│   └── aws/                  user-data.sh · README.md (sin credenciales)
├── escenarios/               mod-1.sh · mod-2.sh · mod-3.sh · escenario-6.sh · escenario-8.sh · esquemas.py
├── herramientas/             generador_carga.py · medir_latencia.py · cargar_acreditaciones.py
├── postman/                  colección + entornos (local, aws)
├── docs/                     01-especificacion.md · 02-plan-tecnico.md · 03-tareas.md
│                             decisiones.md (anexo) · actividades.md · resultados/
├── docker-compose.yml
├── .env.example
└── README.md
```

`src/gestion_trabajos` se mueve a `servicios/gestion_trabajos/` con `git mv`, para conservar la historia. **Cada servicio es una carpeta autocontenida**: su propio Dockerfile, sus dependencias, su seedwork y sus pruebas. La estructura de carpetas ya dice que hay cuatro microservicios, no un monolito con cuatro módulos.

**Una imagen, dos tipos de proceso por servicio.** Cada imagen arranca como `api` (gunicorn + Flask) o como `consumidor` (`python -m <servicio>.consumidor`). Sigue siendo **un** microservicio —mismo código, misma base de datos— con dos roles que escalan por separado. Tres razones:

1. **Escenario 8:** `docker compose --scale` sobre el consumidor, sin chocar con el puerto HTTP de la API.
2. **Escenario 6:** detener el reactor es detener `operaciones-consumidor`, que es literalmente lo que dice el escenario (*«deja de consumir»*).
3. **Elimina un defecto actual:** hoy el consumidor corre en un hilo que arranca `create_app`, lo que bajo el reloader de Flask o varios workers de gunicorn puede duplicar consumidores.

---

## 2. Esquemas: formato y versionamiento

### 2.1 Formato: Avro

| Criterio | **Avro** | Protobuf | JSON Schema |
|---|---|---|---|
| Integración con el Schema Registry de Pulsar **desde el cliente Python** | ✅ `pulsar.schema.Record` + `AvroSchema`: registro y chequeo de compatibilidad en el broker al conectar | ⚠️ El tipo de esquema Protobuf nativo es del cliente Java; en Python quedaría como bytes y se pierde la validación en el broker | ✅ `JsonSchema` |
| Tamaño en el cable | Binario, sin nombres de campo | Binario, sin nombres de campo | Texto, con nombres de campo en **cada** mensaje |
| Evolución | Resolución lector/escritor con valores por defecto | Números de campo | Débil: no hay resolución de esquemas |
| Costo de adopción | **Cero**: ya está en uso (`despachadores.py:21`, `consumidores.py:28`) | Reescribir contratos + generación de código | Bajo |

**Por qué Avro, en términos de los escenarios.**

- **El tamaño importa dos veces.** El escenario 6 obliga a *retener* el backlog durante la caída, y el escenario 8 multiplica el volumen. JSON repite los nombres de campo en cada mensaje retenido.
- **La validación en el broker vale más que la comodidad.** Protobuf ganaría en tipado, pero perder el rechazo de esquemas incompatibles en el broker (CA-E2) es perder el mecanismo de gobierno del contrato.
- **No hay que migrar nada.** Avro ya funciona en el código existente.

### 2.2 Mecanismo de versionamiento, en tres niveles

| Nivel | Qué cubre | Mecanismo |
|---|---|---|
| **1 · Evolución compatible** | Agregar o quitar un campo opcional con valor por defecto | Mismo stream. El **Schema Registry de Pulsar** guarda cada versión del esquema por tópico y rechaza al productor o consumidor incompatible al conectarse. Validación obligatoria en el namespace: sin productores sin esquema |
| **2 · Cambio incompatible** | Renombrar un campo, cambiar un tipo, cambiar el significado de un evento | **Event Stream Versioning**: stream nuevo `<nombre>-v2`, publicación dual durante la migración, retiro de `v1` cuando vence su TTL |
| **3 · Semántica** | Qué significa el evento | El campo `type` del sobre CloudEvents lleva la versión: `hogaralpes.trabajo.creado.v1` |

**En el código:** paquetes `schema/v1` en cada servicio. **Cada consumidor tiene su propia copia del contrato**, en coherencia con `TO-7`. La fuente de verdad es el registro del broker, no un paquete Python compartido.

### 2.3 Regla de compatibilidad: `FULL_TRANSITIVE`

Se fija explícitamente en cada namespace (RS-3):

- **`FULL`** (hacia adelante y hacia atrás) porque productores y consumidores se despliegan **en cualquier orden**. MOD-3 exige redesplegar GT solo, con OPS y EMP sin tocar: un lector viejo lee datos nuevos. Y un consumidor que se actualiza antes lee datos viejos.
- **`TRANSITIVE`** (contra *todas* las versiones anteriores, no solo la inmediata) **por el escenario 6.** Un consumidor que vuelve tras una caída lee un backlog que puede traer mensajes escritos con cualquier versión dentro de la ventana de 7 días. La compatibilidad tiene que valer contra todas.

### 2.4 Contratos

Pulsar asocia **un esquema por tópico**, así que cada stream lleva un solo tipo de record y el campo `type` del sobre discrimina el evento.

| Stream | Record | Campos del cuerpo (todos opcionales salvo el id) |
|---|---|---|
| `cmd-trabajo-{región}` | `ComandoCrearTrabajo` (v1 existente) | Los actuales + **`trabajo_id`**: es la evolución compatible de CA-E1 |
| `evt-trabajo-{región}` | `EventoTrabajo` | `trabajo_id`, `partner_id`, `pais`, `ciudad`, `categoria`, `urgencia`, `canal`, `estado`, `estado_anterior` |
| `cmd-acreditacion` | `ComandoAcreditacion` | `acreditacion_id`, `proveedor_id`, `pais`, `ciudad`, `categorias[]`, `nivel`, `vigencia_meses`, `motivo` |
| `evt-acreditacion` | `AcreditacionActualizada` (carga de estado) | Snapshot completo + `version` |
| `evt-emparejamiento` | `EventoEmparejamiento` | `trabajo_id`, `total_candidatos`, `candidatos[]` |

**Sobre común** en todos (RS-2): `id`, `type`, `specversion`, `time`, `service_name`, `datacontenttype` + **`correlation_id`**, que es nuevo.

**Propiedades de mensaje** (no requieren deserializar): `partner_id` (P-1), `region`, `correlation_id`.

`estado` y `categoria` viajan como **texto**, no como enumeración Avro. Una enumeración cerrada rompería MOD-3 (RS-5).

`EventoTrabajo` es un record plano, no una unión de sub-records por tipo. Es más simple de evolucionar y se lee igual para los dos tipos de evento.

### 2.5 Spike T0 — 45 minutos, antes de escribir los consumidores

La demostración CA-E1 depende de un comportamiento concreto del cliente `pulsar-client==3.5.0` que hay que **verificar, no suponer**:

1. ¿El consumidor decodifica con el **esquema del escritor**, obtenido del registro por la versión del mensaje, o con el suyo propio?
2. ¿En qué orden serializa `Record` los campos: declaración o alfabético?
3. ¿Con `FULL_TRANSITIVE` y la actualización automática de esquema habilitada, el productor con un campo nuevo se registra solo?

| Resultado del spike | Regla de evolución que queda |
|---|---|
| El cliente resuelve con el esquema del escritor | Agregar o quitar campos opcionales en cualquier posición |
| No lo resuelve | Campos nuevos **solo al final** del record de nivel superior, siempre opcionales. El consumidor elige su record por la versión de esquema del mensaje. Se documenta como restricción del cliente Python |

El resultado queda escrito en `docs/decisiones.md`. En la sustentación es una respuesta concreta a *«¿cómo sabían que la evolución funcionaba?»*.

---

## 3. Pulsar: tenant, namespaces, tópicos y suscripciones

### 3.1 Namespaces: uno por contexto productor

Cada equipo dueño del stream fija sus políticas. La región va en el nombre del tópico.

| Namespace | Tópicos | Políticas |
|---|---|---|
| `hogar-alpes/trabajos` | `cmd-trabajo-{región}` · `evt-trabajo-{región}` | Ver abajo |
| `hogar-alpes/acreditacion` | `cmd-acreditacion` · `evt-acreditacion` | Ídem |
| `hogar-alpes/emparejamiento` | `evt-emparejamiento` | Ídem |

**Políticas comunes a los tres namespaces:**

| Política | Valor | Por qué |
|---|---|---|
| TTL de mensajes | **7 días** | Es la «ventana de retención» del escenario 6 (spec §5.2) |
| Cuota de backlog | 10 GB · política **`consumer_backlog_eviction`** | Nunca bloquea al productor. Es la configuración que hace posible la respuesta del escenario 6 |
| Retención de confirmados | 1 día / 1 GB | Permite re-leer para depurar; no es la ventana del escenario |
| Compatibilidad de esquema | **`FULL_TRANSITIVE`** | §2.3 |
| Validación de esquema | Obligatoria | Sin productores sin esquema |
| Creación automática de tópicos | **Deshabilitada** | Un nombre mal escrito crearía un tópico sin particiones y sin suscripciones. Solo el script crea tópicos |

### 3.2 Tópicos, claves y suscripciones

Regiones: `andina` (CO) · `norteamerica` (MX) · `conosur` (BR, AR). **4 particiones** por tópico. La asignación país → región vive en `infra/regiones.json`, que es configuración.

| Tópico | Clave | Suscripción | Tipo | Consumidor |
|---|---|---|---|---|
| `cmd-trabajo-{r}` | `trabajo_id` | `gestion-trabajos` | **Shared** | GT consumidor, por patrón `cmd-trabajo-.*` |
| `evt-trabajo-{r}` | `trabajo_id` | `operaciones` | **Failover** | OPS consumidor, por patrón `evt-trabajo-.*` |
| `evt-trabajo-{r}` | `trabajo_id` | `emparejamiento-{r}` | **Failover** | EMP consumidor de la región |
| `cmd-acreditacion` | `proveedor_id` | `acreditacion` | **Failover** | ACR consumidor |
| `evt-acreditacion` | `proveedor_id` | `emparejamiento-proyeccion` | **Failover** | EMP proyección |
| `evt-emparejamiento` | `trabajo_id` | — (E5) | — | — |

**Por qué cada tipo de suscripción.**

- **Shared en comandos de trabajo.** Cada `CrearTrabajo` crea un trabajo distinto, así que no hay orden que preservar, y la creación es idempotente por `trabajo_id`. Se escala sin techo.
- **Failover donde el orden importa.** Una partición tiene un solo consumidor activo, lo que preserva el orden por `trabajo_id` y por `proveedor_id` (una aprobación no puede adelantar a su solicitud).
- **Failover y no Key_Shared en EMP, a propósito.** Con Failover, **el paralelismo máximo es el número de particiones**: una quinta réplica sobre 4 particiones queda ociosa. Eso **hace visible** el punto de sensibilidad del escenario 8 —*«la clave de partición determina el paralelismo máximo»*— en lugar de esconderlo. La medición 1 → 2 → 4 réplicas cabe exactamente en 4 particiones.

### 3.3 Infraestructura como código

- **`infra/pulsar/inicializar.sh`** — idempotente. Corre como servicio de una sola ejecución en Compose, después de que los brokers estén sanos. Crea el tenant, los namespaces, las políticas, los tópicos particionados de `andina` y `norteamerica`, y **pre-crea todas las suscripciones** en posición *earliest*. Así los eventos se retienen para OPS aunque su consumidor nunca haya arrancado (spec §5.2).
- **`infra/pulsar/agregar-region.sh <región>`** — crea los tópicos y las suscripciones de una región nueva. Es el paso «en caliente» de CA-8.4. OPS la descubre sola por su suscripción por patrón; EMP levanta `emparejamiento-<región>`.

---

## 4. Persistencia por servicio

Una instancia de PostgreSQL 16 por servicio, cada una en su propia red Docker y con credenciales propias (CA-T1). Las tablas se crean con `create_all` de SQLAlchemy, como hoy. No se agregan migraciones: no hay datos que migrar.

| Servicio | Modelo | Tabla | Columnas clave | Índices y restricciones |
|---|---|---|---|---|
| GT | CRUD | `trabajos` · `sub_trabajos` | Sin cambios | `id` = `trabajo_id` del productor → creación idempotente |
| OPS | CRUD | `seguimientos_operativos` | Las actuales | `UNIQUE(trabajo_id)` |
| OPS | CRUD | `eventos_procesados` | `evento_id` (PK), `tipo`, `resultado` ∈ {APLICADO, DUPLICADO, HUERFANO}, `fecha` | Idempotencia + conteos de CA-6.4 y CA-6.5 |
| EMP | CRUD (proyección) | `proveedores_candidatos` | `proveedor_id`, `categoria`, `pais`, `ciudad`, `nivel`, `estado`, `vigente_hasta`, `version` | PK (`proveedor_id`, `categoria`) · índice parcial (`pais`, `ciudad`, `categoria`) `WHERE estado='ACREDITADA'` |
| EMP | CRUD | `emparejamientos` | `trabajo_id` (PK), `region`, `criterio`, `candidatos` (JSONB), `total`, `fecha` | — |
| ACR | **Event Sourcing** | `eventos_acreditacion` | `id`, `agregado_id`, `version`, `tipo`, `datos` (JSONB), `ocurrido_en` | `UNIQUE(agregado_id, version)` = concurrencia optimista |

**Upsert de la proyección.** Se reemplazan las filas de ese proveedor **solo si la versión entrante es mayor que la almacenada**. Así la proyección es idempotente y tolerante al desorden.

**Event Sourcing en ACR.**

- **Escritura:** se cargan los eventos del agregado por versión, se reconstruye el estado, el comando valida contra ese estado, se agrega el evento nuevo con `version + 1`, commit, y después del commit se publica el snapshot (`AcreditacionActualizada`) por la misma Unidad de Trabajo que ya usa GT.
- **Lectura:** se reconstruye el estado desde el log. Sin snapshots de agregado: con pocos eventos por acreditación no se justifican.

---

## 5. Seedwork: se mantiene `TO-7` (copia por servicio)

Para cuatro servicios se re-evaluó si convenía extraer una biblioteca compartida. **Se mantiene la copia.**

| | Copia por servicio (`TO-7`) | Biblioteca compartida |
|---|---|---|
| Acoplamiento | Ninguno en compilación | Todos dependen de su versión (`PS-8`) |
| Costo de un arreglo | ×4 | ×1, pero redespliegue coordinado |
| Costo de montarlo en 2 días | Copiar y renombrar el paquete | Empaquetar, versionar y publicar en un índice o git; ajustar los cuatro Dockerfile |

La decisión de la Entrega 2 se tomó para nueve servicios; con cuatro, la multiplicación del costo es menor y el argumento a favor de la copia se sostiene mejor. Cada copia se **recorta** a lo que el servicio usa.

**Un ejemplo real del costo aceptado, útil para la sustentación.** El arreglo del despachador (G-3a: un productor reutilizado por proceso en lugar de un cliente por mensaje) se hace **cuatro veces**, una por servicio. Eso es exactamente lo que `TO-7` dice que se paga.

---

## 6. Despliegue

### 6.1 Pulsar: clúster multinodo en Compose

| Componente | Instancias | Memoria aprox. |
|---|---|---|
| ZooKeeper (metadatos) | 1 | 512 MB |
| Inicialización de metadatos del clúster | 1, una sola ejecución | — |
| BookKeeper (bookies: el log durable) | **2** | 1 GB c/u |
| Brokers | **2** | 1,5 GB c/u |
| Configuración (`inicializar.sh`) | 1, una sola ejecución | — |

- **Quórums:** ensemble 2 · escritura 2 · confirmación 2. Cada entrada del log queda en los dos bookies antes de confirmarse al productor. **Eso es la «durabilidad» del escenario 6**, no una palabra en una lámina.
- **Dos brokers** reparten las particiones del escenario 8. Los clientes usan `pulsar://broker-1:6650,broker-2:6650`.
- Imagen `apachepulsar/pulsar:3.2.2`, la misma que ya usa el repositorio.

**Por qué no standalone.** La rúbrica dice *«configuró, desplegó y usó un cluster»* (5 pt). Standalone mete todos los componentes en un proceso: vale como entorno de desarrollo, pero no permite mostrar replicación entre bookies ni reparto entre brokers. **Contingencia** (§10): si el clúster consume más de 2 horas de depuración, se vuelve a standalone manteniendo `inicializar.sh` intacto, porque la API de administración es la misma.

### 6.2 AWS

| Aspecto | Decisión |
|---|---|
| Cómputo | 1 EC2 **t3.xlarge** (4 vCPU, 16 GB), Ubuntu 24.04, disco gp3 de 40 GB |
| Aprovisionamiento | `infra/aws/user-data.sh`: instala Docker y el plugin de Compose, clona el repositorio público, `cp .env.example .env`, `docker compose up -d`. Los pasos quedan en `infra/aws/README.md` |
| Red | Security group con 22 (SSH) solo desde las IP del equipo · 8000-8003 (las cuatro API) abiertos durante la sustentación · **Pulsar y PostgreSQL no se exponen**: su administración va por SSH |
| Costo | ≈ USD 0,17/h en us-east-1 → ≈ USD 4/día. **Se detiene cuando no se usa** |
| Secretos | Nada de AWS en el repositorio. Credenciales de base de datos en `.env`, generado en la VM |

**Por qué EC2 + Compose y no ECS, EKS o un Pulsar gestionado.**

- **Es el mismo artefacto en local y en la nube.** Lo que el equipo prueba en su máquina es lo que corre en AWS. Con dos días, eso elimina una clase entera de fallas.
- **ECS y EKS** exigen volúmenes persistentes para los bookies y un chart de Pulsar pesado. No cabe en el plazo.
- **Pulsar gestionado** (por ejemplo StreamNative) contradice el ítem de la rúbrica: el clúster lo debe configurar y desplegar el equipo.

**Si usan AWS Academy (Learner Lab):** verificar el primer día que permita `t3.xlarge`. Si no, usar `t3.large` (8 GB) con la contingencia de Pulsar standalone.

### 6.3 Redes Docker: el aislamiento se hace cumplir, no se promete

| Red | Qué conecta |
|---|---|
| `red-broker` | Pulsar + todos los procesos de servicio |
| `red-gt` · `red-ops` · `red-emp` · `red-acr` | Cada servicio con **su** PostgreSQL |

**Ningún servicio comparte red con otro servicio.** Una llamada HTTP entre servicios no puede resolverse ni por nombre ni por IP. RNF-1 y CA-T1 quedan demostrados por construcción, no por disciplina.

---

## 7. Cómo se mantienen los escenarios de modificabilidad

| Escenario | Qué cambia en la Entrega 4 | Cómo se verifica | Riesgo |
|---|---|---|---|
| **MOD-1** | **Nuevo:** `RepositorioTrabajosMemoria` y selección por `ADAPTADOR_TRABAJOS=postgres\|memoria` en `infraestructura/fabricas.py`, que es el único archivo que conoce el motor. No es un adaptador de juguete: es el que usan las pruebas de la capa de aplicación | `escenarios/mod-1.sh`: levanta GT con `memoria`, corre las carpetas de Postman de los escenarios 2 y 3, y verifica que `git diff --stat` del commit que agregó el adaptador no toca `dominio/` ni `aplicacion/` | Bajo |
| **MOD-2** | **Nada.** `reglas_regionales.json` no se toca | Carpeta de Postman del escenario 2, sin cambios · `escenarios/mod-2.sh` agrega un país y reinicia el sidecar | Bajo |
| **MOD-3** | Se vuelve **entre servicios**: el estado viaja como texto en `EventoTrabajo` | `escenarios/mod-3.sh`: registra el `StartedAt` de los contenedores de OPS y EMP, aplica un parche que agrega el estado `EN_PAUSA` (`EN_EJECUCION ↔ EN_PAUSA`), reconstruye **solo** GT, transiciona un trabajo y verifica: OPS registra `EN_PAUSA` · `StartedAt` de OPS y EMP intacto · 0 errores de deserialización. Al final revierte el parche | Medio: depende de G-2 resuelto |
| **Pruebas** | `tests/` se mueve con el servicio. Se agregan pruebas del adaptador en memoria | `pytest` por servicio | Bajo |
| **Postman** | Se elimina *«Eventos de dominio entre módulos»* (G-6). Se agrega *«Eventos de integración entre servicios»*, que consulta la API de OPS con reintentos y tiempo límite (R-4). Hay entornos `local` y `aws` | `newman` en verde en los dos entornos | Bajo |

**Orden de trabajo en GT para no romperlo:**

1. Mover el servicio a `servicios/` y verificar que la colección sigue en verde.
2. Separar la API del consumidor.
3. Cambiar el despachador y los tópicos.
4. Retirar el módulo `operaciones`.

Cada paso es un commit con la colección en verde.

---

## 8. Extracción de `operaciones`

1. Copiar `modulos/operaciones/{dominio,aplicacion,infraestructura}` a `servicios/operaciones/src/operaciones/`, con su seedwork.
2. **Reemplazar el handler de señales `pydispatch` por una capa anticorrupción** en `infraestructura/consumidores.py`. Por cada mensaje de `evt-trabajo-.*`:
   - deduplicar por `evento_id`;
   - traducir a `AbrirSeguimiento` o `RegistrarCambioEstado`;
   - ejecutar en **su** Unidad de Trabajo;
   - confirmar el mensaje (`ack`) **después** del commit;
   - si hay excepción, `negative_acknowledge` para que Pulsar lo reentregue.
3. Si llega un cambio de estado sin seguimiento, se registra como `HUERFANO` en `eventos_procesados`. **No se descarta en silencio** (CA-6.5).
4. API propia: `GET /seguimientos/{trabajoId}`, `GET /seguimientos/conteo?desde=`, `GET /health`.
5. En GT: borrar el módulo, sus modelos, su `create_all` y el endpoint `/seguimiento`.

---

## 9. Scripts de escenario y herramientas

| Artefacto | Qué hace | Criterios que cubre |
|---|---|---|
| `herramientas/generador_carga.py` | Publica `CrearTrabajo` en `cmd-trabajo-{r}` a una tasa y durante un tiempo dados; con la opción `--via-http`, usa `POST /trabajos`. Simula el Gateway o BFF de la E5 | 6, 8 |
| `herramientas/medir_latencia.py` | Peticiones concurrentes contra un endpoint → p50, p95, p99 y tasa de error. Solo biblioteca estándar | CA-6.2, CA-8.2 |
| `herramientas/cargar_acreditaciones.py` | 100.000 × (`SolicitarAcreditacion` + `AprobarAcreditacion`) por `cmd-acreditacion` | CA-8.1 |
| `escenarios/escenario-6.sh` | Línea base → `docker compose stop operaciones-consumidor` → carga durante *T* → estadísticas de las suscripciones → reinicio → conteos. Parámetros `N` y `T` | CA-6.1 … 6.6 |
| `escenarios/escenario-8.sh` | Carga de proyección → latencia de consulta → drenaje con *k* = 1, 2, 4 → `agregar-region.sh conosur` bajo carga | CA-8.1 … 8.6 |
| `escenarios/esquemas.py` | Productor con campo nuevo aceptado; productor con cambio incompatible rechazado | CA-E1, CA-E2 |

Cada script imprime **PASA/FALLA por criterio** (RNF-8) y guarda su salida en `docs/resultados/<escenario>-<fecha>.md`. Esa salida es la evidencia para la rúbrica y el insumo de la Entrega 5.

---

## 10. Calendario y líneas de corte

| Cuándo | Frente A | Frente B | Frente C |
|---|---|---|---|
| **Día 1 · 11 sep** (tarde y noche) | Spike T0 · clúster Pulsar + `inicializar.sh` | Mover GT a `servicios/` · separar API y consumidor | Esqueleto de ACR (seedwork, event store) |
| **Día 2 · 12 sep** | GT: despachador, tópicos regionales, adaptador en memoria · aprovisionar EC2 | OPS extraído + `escenario-6.sh` | ACR completo + EMP (proyección y consumidor regional) |
| **Día 2 · noche** | Integración de los cuatro servicios en local · colección en verde | | |
| **Día 3 · 13 sep** | Despliegue en AWS + Postman contra AWS | Corridas de los escenarios 6 y MOD · `docs/decisiones.md` | Corrida del escenario 8 · README · `docs/actividades.md` |

La asignación de frentes a personas va en la Fase 3. Cada frente entra por **su propio PR** desde la cuenta de quien lo hace (R-1).

**Líneas de corte, en el orden en que se sacrifican:**

1. CA-6.7 (demostración de la expiración por TTL).
2. La medición con 4 réplicas. La de 1 → 2 se conserva siempre.
3. Clúster multinodo → standalone, si la depuración supera 2 horas. `inicializar.sh` no cambia.
4. Carga de 100.000 por comandos → si ACR es demasiado lento, se publican los snapshots directo en `evt-acreditacion`. CA-8.1 se sigue cumpliendo, porque la proyección sigue alimentándose **solo por eventos**.
5. CA-8.4 (región en caliente) → se deja documentado como procedimiento y se demuestra en vivo en la sustentación.

**No se corta nunca:** los cuatro servicios corriendo · comunicación solo por Pulsar · base de datos en los cuatro · despliegue en AWS · README · documento de actividades · la colección de Postman en verde.

---

## 11. Riesgos técnicos nuevos

| # | Riesgo | Mitigación |
|---|---|---|
| RT-1 | El cliente Python de Pulsar no resuelve con el esquema del escritor y CA-E1 falla | Spike T0 y regla alternativa (§2.5) |
| RT-2 | ~22 contenedores no caben en la memoria de Docker Desktop de un portátil | Asignar ≥ 10 GB a Docker; si no alcanza, se trabaja contra la EC2 o en standalone |
| RT-3 | Límites de tipo de instancia en AWS Academy | Verificarlo el día 1 (§6.2) |
| RT-4 | El rebalanceo de Failover al agregar réplicas distorsiona la medición de throughput | Se mide el drenaje de un backlog precargado **después** de que los consumidores estén conectados, no durante la conexión |
| RT-5 | El consumidor en un hilo dentro de Flask se duplica con el reloader o con varios workers | Resuelto por diseño: proceso `consumidor` separado (§1) |
