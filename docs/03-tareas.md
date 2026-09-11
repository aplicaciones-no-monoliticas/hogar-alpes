# Entrega 4 · Tareas — Fase 3 `/tasks`

| Estado | Base | Entrega | Equipo |
|---|---|---|---|
| **Borrador para aprobación** | `01-especificacion.md` · `02-plan-tecnico.md` (aprobados) | **2026-09-13** | **A** = Andrés Gómez · **S** = Stiven Cardona · **J** = Juan Manuel Domínguez |

**Convención de servicio:** 🔧 ajuste sobre el servicio existente · 🆕 servicio nuevo desde cero · ⚙️ infraestructura, herramientas o documentos.

**Convención de trabajo:** una rama por bloque, un PR por bloque, desde la cuenta de quien lo hace. El enunciado exige que las contribuciones sean **equitativas y visibles en commits y PR**; el reparto de abajo es lo que hace verificable ese ítem.

---

## 0. Camino crítico

Cuatro tareas bloquean a todo lo demás. Van primero, hoy:

```
INF-0 (spike)  ──►  CON-1 (contratos Avro)  ──┬──►  OPS-2   consumidor de Operaciones
                                              ├──►  EMP-3   consumidor de Emparejamiento
                                              └──►  GT-3    stream unificado
INF-1 (estructura) ──►  INF-6 (plantilla de servicio)  ──►  OPS-1 · EMP-1 · ACR-1
INF-2 (clúster)    ──►  INF-3 (políticas y tópicos)    ──►  todo consumidor y productor
```

**CON-1 existe para desbloquear el paralelismo:** los contratos Avro se definen una vez y se copian a cada servicio, así S y J no esperan a que A termine Gestión de Trabajos.

### Orden de arranque de las primeras tres horas

| # | Quién | Qué |
|---|---|---|
| 1 | A | INF-0, INF-1, INF-2 |
| 2 | A | CON-1, INF-3, INF-6 |
| 3 | S y J | Con INF-6 listo: OPS-1, ACR-1, EMP-1 en paralelo |

---

## 1. Fundaciones e infraestructura — Andrés

| ID | Tarea | Tipo | Depende de | Verificación | Est. |
|---|---|---|---|---|---|
| **INF-0** | **Spike de esquemas** (plan §2.5): ¿el consumidor decodifica con el esquema del escritor? ¿orden de campos? ¿auto-registro con `FULL_TRANSITIVE`? | ⚙️ | — | Script que imprime las tres respuestas · regla de evolución escrita en `docs/decisiones.md` | 45 min |
| **INF-1** | Estructura del repositorio: crear `servicios/`, `git mv` de Gestión de Trabajos, ajustar Dockerfile, `pytest.ini` y rutas | 🔧 | — | `pytest` verde · `docker compose up` levanta GT como antes · colección actual en verde | 1 h |
| **INF-2** | Clúster de Pulsar en Compose: ZooKeeper, inicialización de metadatos, **2 bookies**, **2 brokers**, healthchecks | ⚙️ | — | `pulsar-admin clusters list` · `bookies list-bookies` muestra 2 · `brokers list` muestra 2 | 2 h |
| **INF-3** | `infra/pulsar/inicializar.sh` idempotente: tenant, 3 namespaces, políticas (TTL 7d, cuota con desalojo, `FULL_TRANSITIVE`, validación obligatoria, creación automática deshabilitada), tópicos de `andina` y `norteamerica` con 4 particiones, **suscripciones pre-creadas en posición *earliest*** | ⚙️ | INF-2 | Correrlo dos veces no falla · `namespaces policies` muestra cada política · `topics list` y `topics stats` muestran las suscripciones sin consumidor | 2 h |
| **INF-4** | `infra/pulsar/agregar-region.sh <región>`: tópicos y suscripciones de una región nueva | ⚙️ | INF-3 | Crea `conosur` y `topics stats` la muestra con su suscripción | 30 min |
| **INF-5** | 4 PostgreSQL, **redes Docker separadas** (una por servicio + `red-broker`), `.env.example` | ⚙️ | INF-1 | Desde el contenedor de un servicio, `getent hosts` de otro servicio **no resuelve** (CA-T1, RNF-1) | 1 h |
| **CON-1** | **Contratos Avro de los 5 streams** (plan §2.4): sobre con `correlation_id`, `EventoTrabajo` plano, `ComandoCrearTrabajo` con `trabajo_id`, `ComandoAcreditacion`, `AcreditacionActualizada`, `EventoEmparejamiento` | ⚙️ | INF-0 | Un script publica y consume un mensaje de cada stream contra el clúster · el registro muestra el esquema por tópico | 1,5 h |
| **INF-6** | **Plantilla de servicio**: seedwork recortado, `config/` (base de datos, broker con **productor reutilizado**), doble punto de entrada `api` \| `consumidor`, Dockerfile, requirements | ⚙️ | INF-1 | Un servicio de ejemplo arranca en los dos modos y responde `/health` | 2 h |

---

## 2. `gestion_trabajos` — ajustes — Andrés 🔧

| ID | Tarea | Depende de | Verificación | Est. |
|---|---|---|---|---|
| **GT-1** | Separar API y consumidor: gunicorn para la API, proceso aparte para el consumidor, quitar el hilo de `create_app` (RT-5) | INF-1, INF-6 | Dos contenedores arriba · `/health` responde · el consumidor aparece en `topics stats` una sola vez | 1 h |
| **GT-2** | Despachador nuevo: cliente y productor reutilizados por proceso (G-3a), `partition_key`, propiedades `partner_id`, `region`, `correlation_id` | CON-1, INF-6 | Publicar 1.000 eventos sin abrir 1.000 conexiones (log y `topics stats`) | 1,5 h |
| **GT-3** | **Stream unificado `evt-trabajo-{región}`** (resuelve G-2): `EventoTrabajo` plano, enrutamiento país → región desde `infra/regiones.json`, retirar los dos tópicos por tipo | GT-2, INF-3 | Crear un trabajo CO y otro MX → cada evento cae en su tópico regional · los eventos de un mismo `trabajoId` caen en la misma partición | 2 h |
| **GT-4** | `CrearTrabajo` con `trabajo_id` opcional del productor + creación **idempotente** + consumidor por patrón `cmd-trabajo-.*` (Shared) | GT-3 | Publicar el mismo comando dos veces crea **un** trabajo · la evolución del esquema es aceptada por el registro (insumo de CA-E1) | 1,5 h |
| **GT-5** | **Retirar el módulo `operaciones`**: código, modelos, `create_all` y el endpoint `/seguimiento` (G-6) | OPS-3 | `pytest` verde · no queda ninguna referencia a `operaciones` en el servicio | 45 min |
| **GT-6** | **MOD-1**: `RepositorioTrabajosMemoria` + selección por `ADAPTADOR_TRABAJOS`, usado por las pruebas de la capa de aplicación | GT-1 | El servicio corre con `memoria` y pasa Postman · `git diff --stat` del commit no toca `dominio/` ni `aplicacion/` | 1,5 h |
| **GT-7** | Regresión: pruebas y colección de GT en verde después de todo lo anterior | GT-3…GT-6 | `pytest` + `newman` en verde | 30 min |

---

## 3. `operaciones` — nuevo — Stiven 🆕

| ID | Tarea | Depende de | Verificación | Est. |
|---|---|---|---|---|
| **OPS-1** | Esqueleto: plantilla, seedwork propio, dominio y aplicación traídos del módulo actual (`SeguimientoOperativo`, `VentanaSLA`, política de SLA) | INF-6 | `pytest` del dominio verde sin base de datos ni broker | 1,5 h |
| **OPS-2** | **Consumidor Pulsar**: patrón `evt-trabajo-.*`, Failover, **capa anticorrupción** evento → comando (`AbrirSeguimiento`, `RegistrarCambioEstado`), Unidad de Trabajo propia, `ack` **después** del commit, `nack` ante excepción | OPS-1, CON-1, INF-3 | Crear un trabajo en GT → aparece el seguimiento en la base de OPS · matar el consumidor a mitad de proceso y verificar reentrega | 3 h |
| **OPS-3** | Idempotencia y API: `eventos_procesados` (APLICADO / DUPLICADO / HUERFANO — **nada se descarta en silencio**), `GET /seguimientos/{trabajoId}`, `GET /seguimientos/conteo`, `/health` | OPS-2 | Reentregar el mismo evento no duplica · un cambio de estado sin seguimiento queda como HUERFANO y es contable | 2 h |
| **OPS-4** | Pruebas: deduplicación, huérfano, orden por `trabajoId` | OPS-3 | `pytest` verde | 1 h |

---

## 4. `acreditacion` — nuevo — Juan Manuel 🆕

| ID | Tarea | Depende de | Verificación | Est. |
|---|---|---|---|---|
| **ACR-1** | Esqueleto y dominio: agregación `Acreditacion`, VOs `NivelAcreditacion`, `Vigencia`, `EstadoAcreditacion`, homologaciones por categoría, reglas de transición, eventos de dominio | INF-6 | `pytest` del dominio verde sin infraestructura | 2 h |
| **ACR-2** | **Event store**: tabla `eventos_acreditacion`, repositorio de append y **rehidratación por reproducción**, `UNIQUE(agregado_id, version)` como concurrencia optimista | ACR-1 | Dos escrituras con la misma versión: la segunda falla · el estado reconstruido coincide con el esperado | 2,5 h |
| **ACR-3** | Comandos y publicación: `SolicitarAcreditacion`, `AprobarAcreditacion`, `RevocarAcreditacion` · consumidor de `cmd-acreditacion` (Failover) · **snapshot `AcreditacionActualizada` publicado después del commit** | ACR-2, CON-1, INF-3 | Publicar solicitud y aprobación → dos eventos en el store y dos snapshots en `evt-acreditacion`, en orden | 2,5 h |
| **ACR-4** | Consultas: `GET /acreditaciones/{id}` (reconstruida desde el log), `GET /acreditaciones/{id}/eventos` (el historial), `/health` | ACR-2 | El historial muestra la secuencia completa: es la evidencia del ítem de Event Sourcing | 1 h |
| **ACR-5** | Pruebas: reconstrucción, concurrencia optimista, comando repetido | ACR-3 | `pytest` verde | 1 h |

---

## 5. `emparejamiento` — nuevo — Juan Manuel 🆕

| ID | Tarea | Depende de | Verificación | Est. |
|---|---|---|---|---|
| **EMP-1** | Esqueleto y dominio: `Emparejamiento`, `CriterioBusqueda`, `Candidato`, regla *«solo acreditación vigente»*, **puerto** de la proyección | INF-6 | `pytest` del dominio verde | 1,5 h |
| **EMP-2** | **Proyección**: consumidor de `evt-acreditacion`, upsert **por versión**, tabla `proveedores_candidatos` con índice parcial por país, ciudad y categoría | EMP-1, ACR-3 | Un evento viejo no pisa uno nuevo · reprocesar el mismo evento no cambia el resultado | 2,5 h |
| **EMP-3** | **Consumidor regional** de `evt-trabajo-{r}` (Failover) → comando `EmparejarTrabajo` → persistir → publicar `CandidatosIdentificados` o `SinCandidatos` | EMP-1, CON-1, GT-3 | Crear un trabajo en GT → emparejamiento persistido y evento publicado | 2,5 h |
| **EMP-4** | Consultas: `GET /candidatos?categoria=&pais=&ciudad=` (la del escenario 8) y `GET /emparejamientos/{trabajoId}` | EMP-2 | El plan de consulta usa el índice (`EXPLAIN`) | 1 h |
| **EMP-5** | Pruebas: regla de vigencia, idempotencia de la proyección | EMP-4 | `pytest` verde | 1 h |

---

## 6. Herramientas y escenarios

| ID | Tarea | Dueño | Tipo | Depende de | Verificación | Est. |
|---|---|---|---|---|---|---|
| **HER-1** | `generador_carga.py`: publica `CrearTrabajo` a una tasa y por un tiempo dados, con opción `--via-http` | S | ⚙️ | CON-1 | 500 comandos publicados y consumidos | 1 h |
| **HER-2** | `medir_latencia.py`: concurrencia → p50, p95, p99 y errores, solo con biblioteca estándar | J | ⚙️ | — | Corre contra `/health` | 45 min |
| **HER-3** | `cargar_acreditaciones.py`: 100.000 solicitudes y aprobaciones | J | ⚙️ | ACR-3 | Prueba con 1.000 antes de la corrida grande | 1 h |
| **ESC-6** | `escenarios/escenario-6.sh`: línea base → detener el consumidor de OPS → carga durante *T* → estadísticas de backlog → reanudar → conteos. **Imprime PASA/FALLA por criterio CA-6.1…6.6** | S | ⚙️ | OPS-3, HER-1, INF-3 | Corrida con *T* = 3 min en local, en verde | 2,5 h |
| **ESC-8** | `escenarios/escenario-8.sh`: carga de proyección → latencia de consulta → drenaje con *k* = 1, 2, 4 → región nueva en caliente. **PASA/FALLA por CA-8.1…8.6** | J | ⚙️ | EMP-4, HER-2, HER-3, INF-4 | Corrida reducida (10.000 proveedores) en verde antes de la grande | 3 h |
| **ESC-M** | `mod-1.sh`, `mod-2.sh`, `mod-3.sh`. El de MOD-3 aplica un parche que agrega `EN_PAUSA`, reconstruye **solo** GT, y comprueba que OPS y EMP **no se reiniciaron** y que OPS registró el estado nuevo | A | ⚙️ | GT-6, GT-3, OPS-2 | Los tres en verde · el `StartedAt` de OPS y EMP no cambia | 2 h |
| **ESC-E** | `esquemas.py`: campo opcional nuevo aceptado (CA-E1) y esquema incompatible **rechazado** por el broker (CA-E2) | A | ⚙️ | INF-0, GT-4 | La salida muestra la aceptación y el rechazo con su mensaje | 1 h |

---

## 7. Integración, despliegue y documentos

| ID | Tarea | Dueño | Depende de | Verificación | Est. |
|---|---|---|---|---|---|
| **INT-1** | `docker-compose.yml` completo: Pulsar, 4 PostgreSQL, 4 API y los consumidores (incluidos los regionales de EMP), orden de arranque y healthchecks | A | GT-7, OPS-4, ACR-5, EMP-5 | **Desde un clon limpio**, `docker compose up` deja todo sano y el humo en verde (RNF-3) | 2 h |
| **INT-2** | Postman reestructurada: carpeta por escenario, *«Eventos de integración entre servicios»* con reintentos y tiempo límite (R-4), entornos `local` y `aws` | S | INT-1 | `newman` en verde en los dos entornos | 2 h |
| **DEP-1** | AWS: EC2 t3.xlarge, security group, `user-data.sh`, despliegue y `infra/aws/README.md` **sin credenciales** | A | INT-1 | Las cuatro API responden desde fuera · el repositorio no tiene secretos | 2 h |
| **DEP-2** | Corrida de los escenarios contra AWS y captura de resultados en `docs/resultados/` | S y J | DEP-1, ESC-6, ESC-8, ESC-M | Un archivo por escenario con su salida | 1,5 h |
| **DOC-1** | `README.md`: escenarios que se prueban, estructura del proyecto, cómo desplegar, actividades por miembro | A | INT-1 | Un tercero levanta el sistema siguiendo solo el README | 1,5 h |
| **DOC-2** | `docs/decisiones.md`: el anexo de sustentación — tipos de evento, formato y evolución de esquemas, topología de datos, CRUD frente a Event Sourcing, clúster de Pulsar, DDD. Cada quien escribe su parte; A consolida | A, S, J | INT-1 | Cubre los seis ítems de justificación de la rúbrica | 2 h |
| **DOC-3** | `docs/actividades.md`: qué hizo cada integrante, con enlaces a sus commits y PR | A, S, J | DEP-2 | Los tres aparecen con trabajo verificable en el historial | 45 min |
| **DOC-4** | Ensayo de sustentación: cada uno defiende **una decisión que no implementó** | A, S, J | DOC-2 | — | 1 h |

**DOC-4 no es relleno.** El 70% de la nota es la sustentación y el tutor puede preguntarle a cualquiera. Si Stiven solo puede defender Operaciones, el ítem se cae.

---

## 8. Carga por persona

| Persona | Bloques | Horas estimadas |
|---|---|---|
| **Andrés** | Infraestructura, contratos, Gestión de Trabajos, escenarios de modificabilidad y esquemas, integración, AWS, documentos | ≈ 28 h |
| **Stiven** | Operaciones, generador de carga, escenario 6, Postman, resultados | ≈ 14 h |
| **Juan Manuel** | Acreditación, Emparejamiento, herramientas de medición, escenario 8 | ≈ 19 h |

El bloque de Andrés está cargado porque concentra el camino crítico. **Dos traspasos posibles** si va justo de tiempo: `DOC-1` (README) a Stiven y `ESC-E` (esquemas) a Juan Manuel, que ya estará dentro del tema por la proyección.

---

## 9. Definición de terminado

Una tarea está terminada cuando: su verificación corre y pasa · el código está en su PR · y, si cambia una decisión del plan, quedó anotada en `docs/decisiones.md`.

Un bloque está terminado cuando su PR está fusionado con `pytest` y `newman` en verde.
