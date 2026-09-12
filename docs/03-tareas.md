# Entrega 4 · Tareas — Fase 3 `/tasks`

| Estado | Base | Entrega | Equipo |
|---|---|---|---|
| **Aprobadas** (2026-09-11) | `01-especificacion.md` · `02-plan-tecnico.md` (aprobados) | **2026-09-13** | **A** = Andrés Gómez · **S** = Stiven Cardona · **J** = Juan Manuel Domínguez |

**Convención de servicio:** 🔧 ajuste sobre el servicio existente · 🆕 servicio nuevo desde cero · ⚙️ infraestructura, herramientas o documentos.

**Columna Criterio:** a qué criterio de la especificación responde la tarea (`CA-*` de aceptación, `RNF-*` no funcional, `RS-*` de esquema, `G-*` brecha del código actual) y, entre paréntesis, el ítem de la rúbrica que sostiene. Una tarea marcada **Habilitador** no responde a ningún criterio por sí misma: existe porque sin ella otras no se pueden hacer, y se declara así a propósito (ver §10).

**Convención de trabajo:** una rama por bloque, un PR por bloque, desde la cuenta de quien lo hace. El enunciado exige que las contribuciones sean **equitativas y visibles en commits y PR**; el reparto de abajo es lo que hace verificable ese ítem.

---

## 0. Camino crítico

Cuatro tareas bloquean a todo lo demás. Van primero:

```
INF-0 (spike)  ──►  CON-1 (contratos Avro)  ──┬──►  OPS-2   consumidor de Operaciones
                                              ├──►  EMP-3   consumidor de Emparejamiento
                                              └──►  GT-3    stream unificado
INF-1 (estructura) ──►  INF-6 (plantilla de servicio)  ──►  OPS-1 · EMP-1 · ACR-1
INF-2 (clúster)    ──►  INF-3 (políticas y tópicos)    ──►  todo consumidor y productor
```

**CON-1 existe para desbloquear el paralelismo:** los contratos Avro se definen una vez y se copian a cada servicio, así S y J no esperan a que A termine Gestión de Trabajos.

### Orden de arranque

| # | Quién | Qué |
|---|---|---|
| 1 | A | INF-0 ✅, INF-1 ✅, INF-2 ✅ |
| 2 | A | INF-6 ✅ · siguen CON-1 e INF-3 |
| 3 | S y J | **Desbloqueados**: OPS-1, ACR-1 y EMP-1 pueden arrancar ya, copiando `servicios/_plantilla` |

---

## 1. Fundaciones e infraestructura — Andrés

| ID | Tarea | Criterio | Depende de | Verificación | Est. |
|---|---|---|---|---|---|
| **INF-0** ⚙️ ✅ | **Spike de esquemas** (plan §2.5): ¿el consumidor decodifica con el esquema del escritor? ¿orden de campos? ¿auto-registro con `FULL_TRANSITIVE`? | RS-3 · habilita CA-E1, CA-E2 *(esquemas, 5 pt)* | — | ✅ Hecho: `docs/decisiones.md` · `herramientas/spike_esquemas.py` | 45 min |
| **INF-1** 🔧 ✅ | Estructura del repositorio: crear `servicios/`, `git mv` de Gestión de Trabajos, ajustar Dockerfile, `pytest.ini` y rutas | **Habilitador** → sin esto no hay 4 servicios separados · conserva CA-M4 | — | `pytest` verde · `docker compose up` levanta GT como antes · colección actual en verde | 1 h |
| **INF-2** ⚙️ ✅ | Clúster de Pulsar en Compose: ZooKeeper, inicialización de metadatos, **2 bookies**, **2 brokers**, healthchecks | RNF-2 *(clúster de Pulsar, 5 pt)* | — | `pulsar-admin clusters list` · `bookies list-bookies` muestra 2 · `brokers list` muestra 2 | 2 h |
| **INF-3** ⚙️ ✅ | `inicializar.sh` idempotente: tenant, 3 namespaces, políticas (TTL 7d, cuota con desalojo, `FULL_TRANSITIVE`, validación obligatoria, creación automática deshabilitada), tópicos de `andina` y `norteamerica` con 4 particiones, **suscripciones pre-creadas en *earliest*** | RNF-2 · RS-3 · G-4 · habilita CA-6.3 y CA-8.5 *(5 pt + 30 pt)* | INF-2 | Correrlo dos veces no falla · `namespaces policies` muestra cada política · las suscripciones existen sin consumidor | 2 h |
| **INF-4** ⚙️ | `agregar-region.sh <región>`: tópicos y suscripciones de una región nueva | CA-8.4 *(30 pt)* | INF-3 | Crea `conosur` y `topics stats` la muestra con su suscripción | 30 min |
| **INF-5** ⚙️ | 4 PostgreSQL, **redes Docker separadas**, `.env.example` | CA-T1 · RNF-1 *(topología 5 pt + comunicación 20 pt)* | INF-1 | Desde un servicio, `getent hosts` de otro **no resuelve** | 1 h |
| **CON-1** ⚙️ ✅ | **Contratos Avro de los 5 streams** con la regla de INF-0: todo campo `Tipo(default=None, required_default=True)`, y el sobre repetido en cada contrato porque la herencia de `Record` lo pierde | RS-1 · RS-2 · RS-4 · RS-5 · RS-6 *(esquemas, 5 pt)* | INF-0 | ✅ `herramientas/verificar_contratos.py`: los 5 contratos con sobre completo, todos sus campos con `default`, y valores intactos de ida y vuelta | 1,5 h |
| **INF-6** ⚙️ ✅ | **Plantilla de servicio**: seedwork recortado, `config/` (base de datos, broker con **productor reutilizado**), doble punto de entrada `api` \| `consumidor`, Dockerfile, requirements | **Habilitador** → base de OPS, EMP y ACR · sostiene RNF-5 y RNF-7 | INF-1 | Un servicio de ejemplo arranca en los dos modos y responde `/health` | 2 h |

---

## 2. `gestion_trabajos` — ajustes — Andrés 🔧

| ID | Tarea | Criterio | Depende de | Verificación | Est. |
|---|---|---|---|---|---|
| **GT-1** | Separar API y consumidor: gunicorn para la API, proceso aparte para el consumidor, quitar el hilo de `create_app` | RT-5 · habilita CA-8.3 *(30 pt)* | INF-1, INF-6 | Dos contenedores arriba · `/health` responde · el consumidor aparece una sola vez en `topics stats` | 1 h |
| **GT-2** | Despachador nuevo: cliente y productor reutilizados por proceso, `partition_key`, propiedades `partner_id`, `region`, `correlation_id` | G-3a · RNF-4 · habilita CA-8.3 *(30 pt)* | CON-1, INF-6 | Publicar 1.000 eventos sin abrir 1.000 conexiones | 1,5 h |
| **GT-3** | **Stream unificado `evt-trabajo-{región}`**: `EventoTrabajo` plano, enrutamiento país → región por configuración, retirar los tópicos por tipo | **G-2** · CA-6.5 · CA-8.5 *(30 pt)* | GT-2, INF-3 | Un trabajo CO y otro MX caen en su tópico regional · los eventos de un mismo `trabajoId`, en la misma partición | 2 h |
| **GT-4** | `CrearTrabajo` con `trabajo_id` opcional + creación **idempotente** + consumidor por patrón `cmd-trabajo-.*` (Shared) | CA-E1 · RNF-4 *(esquemas 5 pt + 30 pt)* | GT-3 | El mismo comando dos veces crea **un** trabajo · el registro acepta la evolución | 1,5 h |
| **GT-5** | **Retirar el módulo `operaciones`**: código, modelos, `create_all` y el endpoint `/seguimiento` | **G-6** · RNF-1 *(comunicación, 20 pt)* | OPS-3 | `pytest` verde · sin referencias a `operaciones` en el servicio | 45 min |
| **GT-6** | **MOD-1**: `RepositorioTrabajosMemoria` + selección por `ADAPTADOR_TRABAJOS`, usado por las pruebas de aplicación | **CA-M1** · **G-5** *(30 pt)* | GT-1 | Corre con `memoria` y pasa Postman · `git diff --stat` no toca `dominio/` ni `aplicacion/` | 1,5 h |
| **GT-7** | Regresión: pruebas y colección de GT en verde tras todos los cambios | **CA-M4** *(30 pt)* | GT-3…GT-6 | `pytest` + `newman` en verde | 30 min |

---

## 3. `operaciones` — nuevo — Stiven 🆕

| ID | Tarea | Criterio | Depende de | Verificación | Est. |
|---|---|---|---|---|---|
| **OPS-1** | Esqueleto: plantilla, seedwork propio, dominio y aplicación traídos del módulo actual | **Habilitador** → base de OPS-2 · sostiene RNF-7 *(DDD)* | INF-6 | `pytest` del dominio verde sin base de datos ni broker | 1,5 h |
| **OPS-2** | **Consumidor Pulsar**: patrón `evt-trabajo-.*`, Failover, **capa anticorrupción** evento → comando, Unidad de Trabajo propia, `ack` después del commit, `nack` ante excepción | **G-1** · CA-6.4 · RNF-1 · RNF-4 *(30 pt + 20 pt)* | OPS-1, CON-1, INF-3 | Crear un trabajo en GT → aparece el seguimiento · matar el consumidor a mitad y verificar reentrega | 3 h |
| **OPS-3** | Idempotencia y API: `eventos_procesados` (APLICADO / DUPLICADO / HUERFANO), `GET /seguimientos/{id}`, `/conteo`, `/health` | **CA-6.4** · **CA-6.5** *(30 pt + CRUD 25 pt)* | OPS-2 | Reentregar el mismo evento no duplica · un cambio sin seguimiento queda HUERFANO y es contable | 2 h |
| **OPS-4** | Pruebas: deduplicación, huérfano, orden por `trabajoId` | Control de riesgo (ver §10) | OPS-3 | `pytest` verde | 1 h |

---

## 4. `acreditacion` — nuevo — Juan Manuel 🆕

| ID | Tarea | Criterio | Depende de | Verificación | Est. |
|---|---|---|---|---|---|
| **ACR-1** | Esqueleto y dominio: agregación `Acreditacion`, VOs, homologaciones, reglas de transición, eventos de dominio | **Habilitador** → base de ACR-2 · sostiene RNF-7 *(DDD)* | INF-6 | `pytest` del dominio verde sin infraestructura | 2 h |
| **ACR-2** | **Event store**: `eventos_acreditacion`, append y **rehidratación por reproducción**, `UNIQUE(agregado_id, version)` | D-5 *(Event Sourcing, 25 pt)* | ACR-1 | Dos escrituras con la misma versión: la segunda falla · el estado reconstruido coincide | 2,5 h |
| **ACR-3** | Comandos y publicación: `Solicitar`, `Aprobar`, `Revocar` · consumidor de `cmd-acreditacion` (Failover) · **snapshot publicado después del commit** | D-6 · RS-1 · habilita CA-8.1 *(20 pt + 25 pt)* | ACR-2, CON-1, INF-3 | Solicitud y aprobación → dos eventos en el store y dos snapshots en `evt-acreditacion`, en orden | 2,5 h |
| **ACR-4** | Consultas: `GET /acreditaciones/{id}` (reconstruida) y `/eventos` (el historial) | *(Event Sourcing, 25 pt — es la evidencia del ítem)* | ACR-2 | El historial muestra la secuencia completa | 1 h |
| **ACR-5** | Pruebas: reconstrucción, concurrencia optimista, comando repetido | Control de riesgo (ver §10) | ACR-3 | `pytest` verde | 1 h |

---

## 5. `emparejamiento` — nuevo — Juan Manuel 🆕

| ID | Tarea | Criterio | Depende de | Verificación | Est. |
|---|---|---|---|---|---|
| **EMP-1** | Esqueleto y dominio: `Emparejamiento`, `CriterioBusqueda`, `Candidato`, regla *«solo acreditación vigente»*, **puerto** de la proyección | **Habilitador** → base de EMP-2 y EMP-3 · refuerza CA-M1 *(DDD)* | INF-6 | `pytest` del dominio verde | 1,5 h |
| **EMP-2** | **Proyección**: consumidor de `evt-acreditacion`, upsert **por versión**, tabla con índice parcial | **CA-8.1** · **CA-8.6** *(30 pt + CRUD 25 pt)* | EMP-1, ACR-3 | Un evento viejo no pisa uno nuevo · reprocesarlo no cambia el resultado | 2,5 h |
| **EMP-3** | **Consumidor regional** de `evt-trabajo-{r}` (Failover) → `EmparejarTrabajo` → persistir → publicar `CandidatosIdentificados` o `SinCandidatos` | **CA-8.3** · **CA-8.5** · RNF-1 *(30 pt + 20 pt)* | EMP-1, CON-1, GT-3 | Crear un trabajo en GT → emparejamiento persistido y evento publicado | 2,5 h |
| **EMP-4** | Consultas: `GET /candidatos?categoria=&pais=&ciudad=` y `GET /emparejamientos/{trabajoId}` | **CA-8.2** *(30 pt)* | EMP-2 | El plan de consulta usa el índice (`EXPLAIN`) | 1 h |
| **EMP-5** | Pruebas: regla de vigencia, idempotencia de la proyección | Control de riesgo (ver §10) | EMP-4 | `pytest` verde | 1 h |

---

## 6. Herramientas y escenarios

| ID | Tarea | Dueño | Criterio | Depende de | Verificación | Est. |
|---|---|---|---|---|---|---|
| **HER-1** ⚙️ | `generador_carga.py`: publica `CrearTrabajo` a una tasa y por un tiempo dados | S | **Habilitador** → sin él no hay escenario 6 ni 8 | CON-1 | 500 comandos publicados y consumidos | 1 h |
| **HER-2** ⚙️ | `medir_latencia.py`: p50, p95, p99 y errores, solo con biblioteca estándar | J | **Habilitador** → instrumento de CA-6.2 y CA-8.2 | — | Corre contra `/health` | 45 min |
| **HER-3** ⚙️ | `cargar_acreditaciones.py`: 100.000 solicitudes y aprobaciones | J | **Habilitador** → instrumento de CA-8.1 | ACR-3 | Prueba con 1.000 antes de la corrida grande | 1 h |
| **ESC-6** ⚙️ | `escenario-6.sh`: línea base → detener el consumidor → carga → backlog → reanudar → conteos | S | **CA-6.1 … CA-6.6** *(30 pt)* | OPS-3, HER-1, INF-3 | Corrida con *T* = 3 min en verde | 2,5 h |
| **ESC-8** ⚙️ | `escenario-8.sh`: proyección → latencia → drenaje con *k* = 1, 2, 4 → región en caliente | J | **CA-8.1 … CA-8.6** *(30 pt)* | EMP-4, HER-2, HER-3, INF-4 | Corrida reducida (10.000 proveedores) en verde | 3 h |
| **ESC-M** ⚙️ | `mod-1.sh`, `mod-2.sh`, `mod-3.sh` | A | **CA-M1 · CA-M2 · CA-M3** *(30 pt)* | GT-6, GT-3, OPS-2 | Los tres en verde · el `StartedAt` de OPS y EMP no cambia | 2 h |
| **ESC-E** ⚙️ | `esquemas.py`: campo nuevo aceptado y esquema incompatible rechazado | A | **CA-E1 · CA-E2** *(esquemas, 5 pt)* | INF-0, GT-4 | La salida muestra la aceptación y el rechazo | 1 h |

---

## 7. Integración, despliegue y documentos

| ID | Tarea | Dueño | Criterio | Depende de | Verificación | Est. |
|---|---|---|---|---|---|---|
| **INT-1** ⚙️ | `docker-compose.yml` completo: Pulsar, 4 PostgreSQL, 4 API y los consumidores | A | **RNF-3** *(código que corre — 30 pt)* | GT-7, OPS-4, ACR-5, EMP-5 | **Desde un clon limpio**, `docker compose up` deja todo sano | 2 h |
| **INT-2** ⚙️ | Postman reestructurada: carpeta por escenario, reintentos por consistencia eventual, entornos `local` y `aws` | S | **CA-M4** · R-4 · evidencia de CA-6.4 *(30 pt)* | INT-1 | `newman` verde en los dos entornos | 2 h |
| **DEP-1** ⚙️ | AWS: EC2 t3.xlarge, security group, `user-data.sh`, despliegue, `infra/aws/README.md` | A | **RNF-6** *(despliegue, 5 pt)* | INT-1 | Las cuatro API responden desde fuera · sin secretos en el repositorio | 2 h |
| **DEP-2** ⚙️ | Corrida de los escenarios contra AWS y captura en `docs/resultados/` | S, J | Evidencia de CA-6.x y CA-8.x *(30 pt + 5 pt)* | DEP-1, ESC-6, ESC-8, ESC-M | Un archivo por escenario con su salida | 1,5 h |
| **DOC-1** ⚙️ | `README.md`: escenarios, estructura, cómo desplegar, actividades | A | RNF-6 *(README — requisito de la guía)* | INT-1 | Un tercero levanta el sistema siguiendo solo el README | 1,5 h |
| **DOC-2** ⚙️ | `docs/decisiones.md`: tipos de evento, esquemas, topología de datos, CRUD vs ES, clúster, DDD | A, S, J | §6 y §7 de la especificación *(tipos de evento 5 pt + topología 5 pt)* | INT-1 | Cubre los seis ítems de justificación | 2 h |
| **DOC-3** ⚙️ | `docs/actividades.md` con enlaces a commits y PR | A, S, J | *(actividades por miembro, 5 pt)* | DEP-2 | Los tres aparecen con trabajo verificable | 45 min |
| **DOC-4** ⚙️ | Ensayo: cada uno defiende **una decisión que no implementó** | A, S, J | Sustentación *(70% de la nota)* | DOC-2 | — | 1 h |

---

## 8. Carga por persona

| Persona | Bloques | Horas estimadas |
|---|---|---|
| **Andrés** | Infraestructura, contratos, Gestión de Trabajos, escenarios MOD y esquemas, integración, AWS, documentos | ≈ 28 h |
| **Stiven** | Operaciones, generador de carga, escenario 6, Postman, resultados | ≈ 14 h |
| **Juan Manuel** | Acreditación, Emparejamiento, herramientas de medición, escenario 8 | ≈ 19 h |

Dos traspasos posibles si Andrés va justo: `DOC-1` a Stiven y `ESC-E` a Juan Manuel.

---

## 9. Definición de terminado

Una tarea está terminada cuando: **su verificación se corrió y pasó** · el código está en su PR · y, si cambió una decisión del plan, quedó anotada en `docs/decisiones.md`. INF-0 es el ejemplo: se corrió, se documentó el hallazgo y se corrigió §2.5 del plan.

Un bloque está terminado cuando su PR está fusionado con `pytest` y `newman` en verde.

---

## 10. Qué mostró la trazabilidad

Al exigirle a cada tarea que citara un criterio, aparecieron dos categorías que conviene tener a la vista:

**Ocho habilitadores** (`INF-1`, `INF-6`, `OPS-1`, `ACR-1`, `EMP-1`, `HER-1`, `HER-2`, `HER-3`) no responden a ningún criterio por sí mismos. No sobran: sin ellos no existen los servicios ni los instrumentos de medición. Quedan declarados como tales para que nadie los confunda con alcance de negocio.

**Tres tareas de pruebas de los servicios nuevos** (`OPS-4`, `ACR-5`, `EMP-5`, ≈ 3 h) **no responden a ningún ítem de la rúbrica.** La guía dice explícitamente que *no* se esperan microservicios completos, y la rúbrica no evalúa pruebas —de hecho advierte que la cobertura es un ejemplo de mala experimentación—. Son control de riesgo para que la demostración no falle en vivo.

**Consecuencia:** si el tiempo aprieta, estas tres son la **primera línea de corte**, antes que las cinco ya previstas en el plan §10. Se recortan a la prueba mínima que protege su escenario: idempotencia en `OPS-4` (sostiene CA-6.4) y regla de vigencia en `EMP-5`. Ninguna otra tarea quedó sin justificación: no hay alcance que nadie pidiera.
