---

description: "Task list template for feature implementation"
---

# Tasks: Saga de asignación de un trabajo, con reversiones y registro de estado

**Input**: Design documents from `/specs/002-saga-asignacion-trabajo/`

**Prerequisites**: plan.md, spec.md, research.md (D1–D10), data-model.md, contracts/ (4 archivos), quickstart.md

**Tests**: Se incluyen tareas de prueba (`test_dominio_*`, `test_aplicacion_*`, `test_correlacion_servicio.py`) porque es el patrón ya establecido en los cuatro servicios existentes y lo exige el Principio VI de la constitución (verificación honesta); no son TDD estricto, pero deben quedar en verde antes de cerrar cada historia.

**Organization**: Las tareas están agrupadas por historia de usuario (spec.md) para permitir implementación y prueba independientes de cada una.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: A qué historia de usuario pertenece (US1, US2, US3)
- Cada tarea incluye la ruta exacta del archivo

## Path Conventions

Repositorio de microservicios existente (ver `plan.md` → Project Structure): `servicios/<servicio>/src/<servicio>/...`, `contratos/v1/`, `infra/pulsar/`, raíz del repo para `docker-compose.yml`, `escenarios/`, `herramientas/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Preparar el servicio nuevo y la infraestructura de contenedores antes de tocar dominio/aplicación.

- [X] T001 Crear `servicios/saga_log/` copiando `servicios/_plantilla/` completa (Dockerfile, requirements.txt, seedwork íntegro incluido `correlacion.py` byte-idéntico); renombrar el paquete `servicio_plantilla` → `saga_log` en `servicios/saga_log/src/saga_log/` y sus imports internos
- [X] T002 [P] Agregar `postgres-saga`, `saga-log`, `saga-log-consumidor` y la red `red-saga` a `docker-compose.yml`, siguiendo el mismo patrón (imagen, healthcheck, variables de entorno) que los cuatro servicios existentes

**Checkpoint**: El esqueleto de `saga_log` existe y compila con `docker compose build saga-log`; ningún otro servicio se modificó todavía.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Contratos extendidos, copias locales de esquema, mecanismo de simulación de fallos y suscripciones de Pulsar — todo lo que las tres historias de usuario necesitan antes de poder implementarse.

**⚠️ CRITICAL**: Ninguna historia de usuario puede empezar hasta que esta fase esté completa.

- [X] T003 [P] Extender `contratos/v1/evt_emparejamiento.py` (`EventoEmparejamiento`): agregar `proveedor_id = String(default='', required_default=True)` y `motivo = String(default='', required_default=True)` al final del esquema, más las constantes `TIPO_PROVEEDOR_PROPUESTO = 'hogaralpes.emparejamiento.proveedor-propuesto.v1'` y `TIPO_CANDIDATOS_LIBERADOS = 'hogaralpes.emparejamiento.candidatos-liberados.v1'`
- [X] T004 [P] Extender `contratos/v1/evt_acreditacion.py` (`AcreditacionActualizada`): agregar `trabajo_id = String(default='', required_default=True)` y `categoria = String(default='', required_default=True)` al final del esquema, más las constantes `TIPO_VIGENCIA_CONFIRMADA = 'hogaralpes.acreditacion.vigencia-confirmada.v1'` y `TIPO_VIGENCIA_RECHAZADA = 'hogaralpes.acreditacion.vigencia-rechazada.v1'`
- [X] T005 Actualizar `herramientas/verificar_contratos.py` para cubrir los dos contratos extendidos por T003/T004 (evolución compatible: ningún campo existente cambia de tipo o posición)
- [X] T006 [P] Sincronizar la copia canónica local `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/infraestructura/schema/v1/evt_emparejamiento.py` con el contrato extendido en T003
- [X] T007 [P] Sincronizar la copia local `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/infraestructura/schema/v1/evt_acreditacion.py` con el contrato extendido en T004
- [X] T008 [P] Crear la copia local `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/infraestructura/schema/v1/evt_emparejamiento.py` (importa `TIPO_*` y la clase `Record` desde el contrato extendido en T003; Gestión de Trabajos no tenía copia de este contrato hasta ahora)
- [X] T009 [P] Crear la copia local `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/infraestructura/schema/v1/evt_acreditacion.py` (mismo patrón, contrato extendido en T004)
- [X] T010 [P] Crear la copia local `servicios/acreditacion/src/acreditacion/modulos/acreditacion/infraestructura/schema/v1/evt_emparejamiento.py` (mismo patrón, contrato extendido en T003; Acreditación no tenía copia de este contrato hasta ahora)
- [X] T011 [P] Crear en `servicios/saga_log/src/saga_log/modulos/sagas/infraestructura/schema/v1/` las tres copias locales de solo lectura: `evt_trabajo.py`, `evt_emparejamiento.py`, `evt_acreditacion.py` (`saga_log` observa los tres streams y no publica ninguno)
- [X] T012 Implementar el paso de la marca `simular_fallo` (D3): `POST /trabajos` acepta el campo JSON opcional `simular_fallo` (`SIN_CANDIDATOS` \| `VIGENCIA` \| `ASIGNACION`, ausente = flujo normal) en `servicios/gestion_trabajos/src/gestion_trabajos/api/trabajos.py`; el comando `CrearTrabajo` la porta hasta `despachadores.py` para que cada mensaje publicado de la cadena (`cmd-trabajo`, `evt-trabajo`) lleve `propiedades['simular_fallo']`, igual mecanismo que `correlation_id`
- [X] T013 [P] Pre-crear en `infra/pulsar/inicializar.sh`/`infra/pulsar/comun.sh` las cuatro suscripciones `Shared` de D6 necesarias para US1/US2: `gestion-trabajos-saga` sobre `evt-emparejamiento`, `acreditacion` sobre `evt-emparejamiento`, `gestion-trabajos-saga` sobre `evt-acreditacion`, `emparejamiento-saga` sobre `evt-acreditacion`
- [X] T014 Confirmar en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/dominio/objetos_valor.py` que `TRANSICIONES` ya declara `CREADO→EMPAREJANDO` (D2 dice que sí, solo falta quien la dispare); si no está declarada, agregarla junto a las transiciones existentes

**Checkpoint**: Contratos extendidos y verificados, copias locales sincronizadas en los cuatro servicios, suscripciones de Pulsar pre-creadas, mecanismo de simulación de fallos listo para que los handlers lo lean. Las historias de usuario pueden empezar.

---

## Phase 3: User Story 1 - Asignación automática de punta a punta (Priority: P1) 🎯 MVP

**Goal**: Crear un trabajo con un proveedor certificado y vigente disponible termina en `ASIGNADO` con ese proveedor, sin intervención manual, recorriendo Gestión de Trabajos → Emparejamiento → Acreditación → Gestión de Trabajos con el mismo `correlation_id`.

**Independent Test**: Crear un trabajo válido con al menos un proveedor certificado y vigente disponible; verificar que termina en estado `ASIGNADO` con el `proveedor_id` visible en `GET /trabajos/{id}`.

### Tests for User Story 1

- [X] T015 [P] [US1] Prueba de dominio: `Trabajo.proveedor_id` y la transición `CREADO→EMPAREJANDO` en `servicios/gestion_trabajos/tests/test_dominio_trabajos.py`
- [X] T016 [P] [US1] Prueba de dominio: reserva exitosa de un candidato (`proveedor_reservado`) en `servicios/emparejamiento/tests/test_dominio_emparejamiento.py`
- [X] T017 [P] [US1] Prueba de dominio/aplicación: upsert de `vigencia_por_proveedor` tolerante al desorden (`version` mayor gana) en `servicios/acreditacion/tests/test_dominio_acreditacion.py`

### Implementation for User Story 1

- [X] T018 [US1] Agregar `proveedor_id: str | None` a la agregación `Trabajo` en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/dominio/entidades.py` y a `TrabajoDTO` en `.../aplicacion/dto.py`
- [X] T019 [US1] Agregar columna `proveedor_id VARCHAR(40) NULL` a la tabla `trabajos` en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/infraestructura/dto.py`, con su mapeo en `infraestructura/mapeadores.py`
- [X] T020 [US1] Exponer `proveedor_id` en la respuesta de `GET /trabajos/{id}` (`MapeadorTrabajoDTOJson.dto_a_externo`) en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/aplicacion/mapeadores.py`
- [X] T021 [US1] `CrearTrabajoHandler` dispara `CREADO→EMPAREJANDO` en el mismo commit que crea el trabajo, en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/aplicacion/comandos/crear_trabajo.py` (depende de T014, T018)
- [X] T022 [US1] Agregar `proveedor_reservado: str | None` a la agregación `Emparejamiento` en `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/dominio/entidades.py`
- [X] T023 [US1] Declarar `RepositorioReservasProveedor` en `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/dominio/repositorios.py`
- [X] T024 [US1] Crear tabla `reservas_proveedor` (`proveedor_id` PK, `trabajo_id` NOT NULL indexado, `categoria` NOT NULL, `reservado_en` NOT NULL) en `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/infraestructura/dto.py` e implementar `RepositorioReservasProveedor` en `infraestructura/repositorios.py` con `try/except IntegrityError` + `db.session.flush()` (D1)
- [X] T025 [US1] `EmparejarTrabajoHandler`: tras calcular la lista completa de candidatos, intentar reservar en orden hasta que uno se deje reservar; publicar `proveedor-propuesto` (con `proveedor_id`) al lograrlo, en `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/aplicacion/comandos/emparejar_trabajo.py` (depende de T023, T024)
- [X] T026 [US1] Crear tabla `vigencia_por_proveedor` (`proveedor_id` + `categoria` PK compuesta, `estado`, `vigente_hasta`, `version`) en `servicios/acreditacion/src/acreditacion/modulos/acreditacion/infraestructura/dto.py`
- [X] T027 [US1] Actualizar `vigencia_por_proveedor` con `upsert` tolerante al desorden dentro de `RepositorioAcreditacionesEventSourcing.agregar` (misma transacción que el event store), en `servicios/acreditacion/src/acreditacion/modulos/acreditacion/infraestructura/repositorios.py` (depende de T026)
- [X] T028 [US1] Nuevo comando + handler de Acreditación para `proveedor-propuesto`: consulta `vigencia_por_proveedor(proveedor_id, categoria)`; si `ACREDITADA` y no vencida, publica `vigencia-confirmada` (con `trabajo_id`, `categoria`); si no, publica `vigencia-rechazada`, en `servicios/acreditacion/src/acreditacion/modulos/acreditacion/aplicacion/comandos/confirmar_vigencia.py` y el consumidor en `infraestructura/consumidores.py` (suscripción `acreditacion` sobre `evt-emparejamiento`, depende de T010, T026)
- [X] T029 [US1] Registrar el hilo del nuevo consumidor de Acreditación en `servicios/acreditacion/src/acreditacion/consumidor.py` (depende de T028)
- [X] T030 [US1] Nuevo comando + handler de Gestión de Trabajos para `vigencia-confirmada`: transiciona `EMPAREJANDO→ASIGNADO`, fija `proveedor_id`, publica `EstadoTrabajoCambiado`, en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/aplicacion/comandos/confirmar_asignacion.py` y el consumidor en `infraestructura/consumidores.py` (suscripción `gestion-trabajos-saga` sobre `evt-acreditacion`, depende de T009, T018, T019)
- [X] T031 [US1] Registrar los hilos de los nuevos consumidores de Gestión de Trabajos (`evt-emparejamiento`, `evt-acreditacion`) en `servicios/gestion_trabajos/src/gestion_trabajos/consumidor.py` (depende de T030)

**Checkpoint**: El camino feliz de punta a punta es funcional y verificable de forma independiente (Caso 1 de `quickstart.md`).

---

## Phase 4: User Story 2 - Reversión limpia cuando algo falla (Priority: P1)

**Goal**: Cuando falla vigencia, no hay candidatos, o falla la asignación final, el sistema revierte automáticamente lo ya hecho: el trabajo termina `CANCELADO` y ningún proveedor queda con una reserva colgada.

**Independent Test**: Provocar cada uno de los tres puntos de falla con `simular_fallo` (`VIGENCIA`, `SIN_CANDIDATOS`, `ASIGNACION`) y verificar que el trabajo termina `CANCELADO` y `reservas_proveedor` queda sin filas huérfanas para ese trabajo.

### Tests for User Story 2

- [X] T032 [P] [US2] Prueba de dominio/aplicación: liberar una reserva es idempotente (un `DELETE` sobre una fila que ya no existe es un no-op) en `servicios/emparejamiento/tests/test_aplicacion_emparejamiento.py`
- [X] T033 [P] [US2] Prueba de dominio: `Trabajo` transiciona `EMPAREJANDO→CANCELADO` en los tres motivos de falla en `servicios/gestion_trabajos/tests/test_dominio_trabajos.py`

### Implementation for User Story 2

- [X] T034 [US2] El handler de `proveedor-propuesto` (T028) respeta la propiedad de mensaje `simular_fallo=VIGENCIA`: publica `vigencia-rechazada` sin consultar `vigencia_por_proveedor`, en `servicios/acreditacion/src/acreditacion/modulos/acreditacion/aplicacion/comandos/confirmar_vigencia.py` (depende de T028)
- [X] T035 [US2] `EmparejarTrabajoHandler` (T025) respeta la propiedad `simular_fallo=SIN_CANDIDATOS`: omite la búsqueda de candidatos y publica `sin-candidatos` directamente, en `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/aplicacion/comandos/emparejar_trabajo.py` (depende de T025)
- [X] T036 [US2] Nuevo comando + handler de Emparejamiento para `vigencia-rechazada`: `DELETE` de `reservas_proveedor` por `trabajo_id` (no-op si no existe), publica `candidatos-liberados` (`motivo=VIGENCIA_RECHAZADA`), en `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/aplicacion/comandos/liberar_reserva.py` y el consumidor en `infraestructura/consumidores.py` (suscripción `emparejamiento-saga` sobre `evt-acreditacion`, depende de T007, T024)
- [X] T037 [US2] Registrar el hilo del nuevo consumidor de Emparejamiento (`ROL_CONSUMIDOR` gana un tercer rol, o el consumidor regional absorbe la suscripción) en `servicios/emparejamiento/src/emparejamiento/consumidor.py` (depende de T036)
- [X] T038 [US2] Nuevo comando + handler de Gestión de Trabajos para `sin-candidatos`: transiciona `EMPAREJANDO→CANCELADO` directo (sin reserva que liberar), publica `EstadoTrabajoCambiado`, en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/aplicacion/comandos/cancelar_sin_candidatos.py` y el consumidor en `infraestructura/consumidores.py` (suscripción `gestion-trabajos-saga` sobre `evt-emparejamiento`, depende de T008, T014)
- [X] T039 [US2] Nuevo comando + handler de Gestión de Trabajos para `vigencia-rechazada`: transiciona `EMPAREJANDO→CANCELADO`, publica `EstadoTrabajoCambiado`, en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/aplicacion/comandos/cancelar_vigencia_rechazada.py`, agregado a `infraestructura/consumidores.py` junto a T030 (depende de T009, T014)
- [X] T040 [US2] El handler de `vigencia-confirmada` (T030) respeta la propiedad `simular_fallo=ASIGNACION`: en vez de asignar, publica `EstadoTrabajoCambiado` a `CANCELADO`, en `servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/aplicacion/comandos/confirmar_asignacion.py` (depende de T030)
- [X] T041 [US2] Extender el consumidor existente de `evt-trabajo` en Emparejamiento: cuando ve `estado-cambiado` a `CANCELADO` para un trabajo con reserva activa propia (falla de asignación final, caso `ASIGNACION`), libera la reserva y publica `candidatos-liberados` (`motivo=ASIGNACION_FALLIDA`), en `servicios/emparejamiento/src/emparejamiento/modulos/emparejamiento/infraestructura/consumidores.py` (depende de T024, T036, T040)

**Checkpoint**: Las tres rutas de compensación funcionan de forma independiente y en conjunto con US1 (Casos 2, 3 y 4 de `quickstart.md`).

---

## Phase 5: User Story 3 - Visibilidad de cada transacción sin leer cuatro bitácoras (Priority: P2)

**Goal**: Consultar en un único endpoint el estado y la línea de tiempo completa de cualquier transacción de asignación, exitosa o compensada, sin correlacionar manualmente los registros de los tres servicios.

**Independent Test**: Con `saga_log` corriendo, ejecutar una transacción completa y una compensada; verificar que `GET /sagas/{trabajo_id}` devuelve el estado final y los pasos en orden cronológico para ambos casos.

### Tests for User Story 3

- [X] T042 [P] [US3] Prueba de aplicación: la tabla de derivación de estado (D9 — qué paso produce qué estado) en `servicios/saga_log/tests/test_aplicacion_sagas.py`
- [X] T043 [P] [US3] Prueba de aplicación: un `mensaje_id` duplicado no duplica un paso en la línea de tiempo (CA-1.14) en `servicios/saga_log/tests/test_aplicacion_sagas.py`
- [X] T044 [P] [US3] Adaptar `test_correlacion_servicio.py` (idéntico al de los otros cuatro servicios) en `servicios/saga_log/tests/test_correlacion_servicio.py`

### Implementation for User Story 3

- [X] T045 [P] [US3] Pre-crear en `infra/pulsar/inicializar.sh`/`infra/pulsar/comun.sh` las tres suscripciones `Shared` de `saga-log` (D6): sobre `evt-trabajo-.*` (patrón, todas las regiones), `evt-emparejamiento`, `evt-acreditacion`
- [X] T046 [P] [US3] Actualizar `servicios/saga_log/src/saga_log/api/salud.py` para responder `{"estado": "UP", "servicio": "saga-log"}`
- [X] T047 [US3] Crear tabla `transacciones_saga` (`trabajo_id` PK, `correlation_id` indexado, `estado`, `iniciada_en`, `terminada_en`) en `servicios/saga_log/src/saga_log/modulos/sagas/infraestructura/dto.py`
- [X] T048 [US3] Crear tabla `pasos_saga` (`id` PK, `mensaje_id` UNIQUE, `trabajo_id` indexado, `correlation_id`, `servicio`, `paso`, `direccion`, `ocurrido_en`) en el mismo `infraestructura/dto.py` (depende de T047)
- [X] T049 [US3] Implementar `direccion` (`AVANCE` \| `REVERSION`) como tabla de mapeo fija por `type`, no persistida, en `servicios/saga_log/src/saga_log/modulos/sagas/infraestructura/repositorios.py`
- [X] T050 [US3] Implementar el repositorio de sagas: `INSERT` de un paso con `try/except IntegrityError` sobre `mensaje_id` (dedupe, CA-1.14) y actualización de `transacciones_saga.estado` según la tabla de D9, en `servicios/saga_log/src/saga_log/modulos/sagas/infraestructura/repositorios.py` (depende de T047, T048, T049)
- [X] T051 [US3] Implementar los tres manejadores de consumidor (`evt-trabajo-.*`, `evt-emparejamiento`, `evt-acreditacion`) que descartan silenciosamente cualquier `type` no reconocido y, si lo reconocen, registran un paso vía T050, en `servicios/saga_log/src/saga_log/modulos/sagas/infraestructura/consumidores.py` (depende de T011, T050)
- [X] T052 [US3] Registrar los tres hilos de consumidor en `servicios/saga_log/src/saga_log/consumidor.py` (depende de T051)
- [X] T053 [P] [US3] Implementar `ObtenerSagaQuery` (por `trabajo_id`, con sus pasos en orden cronológico) en `servicios/saga_log/src/saga_log/modulos/sagas/aplicacion/queries/obtener_saga.py` (depende de T047, T048)
- [X] T054 [P] [US3] Implementar `ObtenerSagasPorEstadoQuery`, incluyendo `INCOMPLETA` calculada (`iniciada_en < ahora - UMBRAL` sobre filas `EN_CURSO`/`COMPENSANDO`) en `servicios/saga_log/src/saga_log/modulos/sagas/aplicacion/queries/obtener_sagas_por_estado.py` (depende de T047)
- [X] T055 [P] [US3] Implementar `ObtenerResumenSagasQuery` (conteo por estado, incluido `INCOMPLETA`) en `servicios/saga_log/src/saga_log/modulos/sagas/aplicacion/queries/obtener_resumen.py` (depende de T047)
- [X] T056 [US3] Implementar `GET /sagas/{trabajo_id}` (404 si no existe), `GET /sagas?estado=`, `GET /sagas/resumen` en `servicios/saga_log/src/saga_log/api/sagas.py` (depende de T053, T054, T055)
- [X] T057 [US3] Confirmar que `servicios/saga_log/src/` no contiene ningún `pulsar.Client().create_producer(...)` ni invocación de `despachadores.py` (CA-1.16); quitar/deshabilitar el despachador copiado de `_plantilla` si quedó sin usar
- [X] T058 [US3] Agregar la variable de entorno `UMBRAL_INCOMPLETA_SEGUNDOS` (default generoso, p. ej. 60) en `servicios/saga_log/src/saga_log/config/` y usarla en T054

**Checkpoint**: Las tres historias de usuario son funcionales; `saga_log` observa sin participar en ninguna decisión de negocio y sobrevive a su propia caída (SC-005).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Automatizar la demostración de los cuatro casos y confirmar que nada existente se rompió.

- [X] T059 [P] Crear `escenarios/saga.sh` (los 4 casos de `quickstart.md`, releyendo del broker/DB lo que produjo cada caso, mismo patrón que `mod-3.sh`/`escenario-8.sh`, reporta PASA/FALLA por CA-1.* en `docs/resultados/saga-<fecha>.md`)
- [X] T060 [P] Verificar que las carpetas 5 y 7 de `postman/hogar-alpes-bff.postman_collection.json` pasan en verde contra el sistema con la saga completa (sin cambios de contenido esperados, CA-1.20)
- [ ] T061 Ejecutar la regresión completa de `quickstart.md`: `pytest` en los cuatro servicios tocados + `saga_log`, `newman` de la colección BFF, `escenarios/escenario-6.sh`, `escenarios/escenario-8.sh`, `escenarios/mod-1.sh`/`mod-2.sh`/`mod-3.sh`; corregir cualquier regresión encontrada (SC-006)
- [ ] T062 [P] Ejecutar `bash escenarios/saga.sh`, confirmar que termina en menos de 5 minutos (SC-004) y que el reporte en `docs/resultados/` queda en verde para los cuatro casos

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — puede empezar de inmediato
- **Foundational (Phase 2)**: Depende de Setup — BLOQUEA las tres historias de usuario
- **User Story 1 (Phase 3)**: Depende de Foundational; es la base funcional de la saga (MVP)
- **User Story 2 (Phase 4)**: Depende de Foundational; reutiliza los handlers de avance creados en US1 (T025, T028, T030) para agregarles las ramas de simulación de fallo y las reversiones — en la práctica conviene completar US1 antes, aunque ambas son P1
- **User Story 3 (Phase 5)**: Depende solo de Foundational (contratos, suscripciones); es un observador puro y no depende funcionalmente de US1/US2, pero para probarla de punta a punta (una transacción completa y una compensada) conviene tener ambas ya implementadas
- **Polish (Phase 6)**: Depende de que las tres historias estén completas

### User Story Dependencies

- **US1 (P1)**: Puede empezar tras Foundational — sin dependencia funcional de otras historias
- **US2 (P1)**: Puede empezar tras Foundational, pero sus tareas de simulación de fallo (T034, T035, T040) extienden handlers que crea US1 (T028, T025, T030) — secuenciar US1 antes de esas tareas puntuales, aunque el resto de US2 (T036–T039, T041) es independiente
- **US3 (P2)**: Puede empezar tras Foundational — observador puro, sin dependencia de código de US1/US2, solo de los contratos extendidos

### Within Each User Story

- Pruebas antes o junto con la implementación del mismo módulo
- Entidades/tablas de dominio antes que comandos/handlers que las usan
- Comandos y handlers antes que el registro de hilos de consumidor
- Historia completa y verificada (checkpoint) antes de continuar a la siguiente

### Parallel Opportunities

- Todas las tareas `[P]` de Setup y Foundational pueden correr en paralelo (archivos distintos)
- Dentro de cada historia, las pruebas marcadas `[P]` pueden correr en paralelo entre sí
- Los tres servicios de dominio (GT, EMP, ACR) pueden avanzar en paralelo dentro de una misma historia una vez Foundational está listo, porque cada uno toca su propia carpeta
- `saga_log` (US3) puede desarrollarse en paralelo a US1/US2 por distintas personas, ya que no comparte archivos con ellas — solo comparte los contratos ya congelados en Foundational

---

## Parallel Example: Foundational

```bash
# Lanzar en paralelo las extensiones de contrato y sus copias locales:
Task: "Extender contratos/v1/evt_emparejamiento.py con proveedor_id/motivo"
Task: "Extender contratos/v1/evt_acreditacion.py con trabajo_id/categoria"
Task: "Crear copia local evt_emparejamiento.py en gestion_trabajos"
Task: "Crear copia local evt_acreditacion.py en gestion_trabajos"
Task: "Crear copia local evt_emparejamiento.py en acreditacion"
Task: "Crear las tres copias locales de solo lectura en saga_log"
```

## Parallel Example: User Story 1

```bash
# Lanzar en paralelo las pruebas de dominio de los tres servicios:
Task: "Prueba de dominio: proveedor_id y CREADO→EMPAREJANDO en gestion_trabajos"
Task: "Prueba de dominio: reserva exitosa en emparejamiento"
Task: "Prueba de dominio/aplicación: upsert de vigencia_por_proveedor en acreditacion"
```

---

## Implementation Strategy

### MVP First (User Story 1 solamente)

1. Completar Phase 1: Setup
2. Completar Phase 2: Foundational (CRÍTICO — bloquea todas las historias)
3. Completar Phase 3: User Story 1
4. **DETENER Y VALIDAR**: Caso 1 de `quickstart.md` — el camino feliz de punta a punta
5. Demostrar si está listo

### Incremental Delivery

1. Setup + Foundational → base lista
2. Agregar US1 → validar Caso 1 → demo (MVP)
3. Agregar US2 → validar Casos 2, 3 y 4 → demo
4. Agregar US3 → validar consultas de `saga_log` sobre lo producido por US1/US2 → demo
5. Polish → `escenarios/saga.sh` automatizado + regresión completa

### Parallel Team Strategy

Con varias personas:

1. El equipo completa Setup + Foundational en conjunto
2. Con Foundational listo:
   - Persona A: Gestión de Trabajos (partes de US1 y US2 en ese servicio)
   - Persona B: Emparejamiento (partes de US1 y US2 en ese servicio)
   - Persona C: Acreditación (partes de US1 y US2 en ese servicio)
   - Persona D: `saga_log` completo (US3), en paralelo desde el principio
3. Las tres historias convergen en los checkpoints de cada fase

---

## Notes

- `[P]` = archivos distintos, sin dependencias pendientes entre sí
- La etiqueta `[Story]` mapea cada tarea a su historia de usuario para trazabilidad
- Cero tópicos nuevos, cero llamadas HTTP entre servicios de dominio, cero relajación del Principio I/II/III/V — ninguna tarea de esta lista debe introducir ninguno de los tres
- `saga_log` nunca publica: verificar T057 explícitamente antes de cerrar US3
- Confirmar en cada tarea de consumidor que el handler es idempotente ante reentrega (Principio V, FR-016) antes de marcarla como terminada
