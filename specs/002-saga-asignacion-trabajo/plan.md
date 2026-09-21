# Implementation Plan: Saga de asignación de un trabajo, con reversiones y registro de estado

**Branch**: `002-saga-asignacion-trabajo` | **Date**: 2026-09-20 | **Spec**: `specs/002-saga-asignacion-trabajo/spec.md`

**Input**: Feature specification from `/specs/002-saga-asignacion-trabajo/spec.md`, más el
documento de diseño de negocio ya aprobado `docs/us-entrega-5/US-01-saga-asignacion-de-trabajo.md`.

## Summary

Convertir la creación de un trabajo en una saga coreografiada de 4 pasos —Gestión de Trabajos →
Emparejamiento → Acreditación → Gestión de Trabajos— sobre los tres tópicos de eventos que ya
existen, sin agregar ninguno nuevo. Emparejamiento pasa de solo *listar* candidatos a *reservar*
uno con una restricción de unicidad en su base de datos; Acreditación gana una proyección de
lectura para confirmar vigencia por proveedor+categoría en el momento de la propuesta; Gestión de
Trabajos gana la transición automática `CREADO→EMPAREJANDO→ASIGNADO` (o `→CANCELADO` por
compensación) y guarda el proveedor asignado. Un servicio nuevo, `saga_log` —nacido de la misma
plantilla que los demás, solo consumidor, sin publicar nada—, observa los tres canales y expone
`GET /sagas/{trabajo_id}`, `GET /sagas?estado=`, `GET /sagas/resumen`. El BFF ya tiene todo el
cableado para `saga-log` desde la entrega anterior y no se modifica.

## Technical Context

**Language/Version**: Python 3.11 (`python:3.11-slim`), igual que los cuatro servicios existentes — restricción de la constitución, no se relaja.

**Primary Dependencies**: Flask 3.0.3, Flask-SQLAlchemy 3.1.1, SQLAlchemy 2.0.30, psycopg2-binary 2.9.9, `pulsar-client[avro]` 3.5.0, fastavro 1.9.4, PyDispatcher 2.0.7, gunicorn 22.0.0 (las mismas de `servicios/_plantilla/requirements.txt`, que `saga_log` copia sin variar versiones).

**Storage**: PostgreSQL 16 — una instancia nueva `postgres-saga` para `saga_log` (Principio I: cada servicio con su propia base), más columnas/tablas nuevas en las bases ya existentes de `gestion_trabajos`, `emparejamiento` y `acreditacion` (ver `data-model.md`).

**Testing**: `pytest` por servicio (patrón ya establecido: `tests/test_dominio_*`, `test_aplicacion_*`, `test_correlacion_servicio.py`), `escenarios/saga.sh` (nuevo, mismo patrón que `mod-3.sh`/`escenario-8.sh`), colección Postman `hogar-alpes-bff.postman_collection.json` (carpetas 5 y 7 ya existen, hoy en rojo a propósito).

**Target Platform**: Contenedores Linux vía `docker compose up -d --build`; despliegue en Kubernetes/AWS es US-03, fuera de alcance de este plan salvo dejar el servicio nuevo construible de la misma forma que los otros cuatro.

**Project Type**: Sistema de microservicios existente (backend puro, sin frontend) — esta historia agrega un quinto servicio de dominio y modifica tres de los cuatro existentes; no aplica ninguna de las plantillas de "single project" ni "web application" tal cual, se documenta la estructura real abajo.

**Performance Goals**: Sin metas nuevas. Se preservan las de la Entrega 4 (consultas <1s con >100k proveedores, degradación <10% durante una caída, escalar un servicio degrada su velocidad <10%) — CA-1.19/SC-006.

**Constraints**:
- Cero tópicos nuevos (FR-018, CA-1.7): toda comunicación nueva es un `type` nuevo sobre uno de los tres streams existentes (`evt-trabajo-{región}`, `evt-emparejamiento`, `evt-acreditacion`).
- Cero llamadas HTTP entre servicios de dominio (Principio I); `saga_log` no publica nada (FR-015, CA-1.16).
- Todo handler nuevo debe ser idempotente ante reentrega al-menos-una-vez (Principio V, FR-016).
- Los consumidores existentes (Operaciones, la proyección de Emparejamiento, el consumidor regional) deben seguir funcionando sin redesplegarse (CA-1.9).
- Las suscripciones nuevas deben pre-crearse en `infra/pulsar/` antes de que el primer mensaje de saga se pierda (Principio V).

**Scale/Scope**: 1 servicio nuevo (`saga_log`) + cambios acotados en 3 de los 4 servicios existentes (dominio, aplicación, infraestructura, cada uno dentro de su propia carpeta) + 2 contratos extendidos (`evt_emparejamiento`, `evt_acreditacion`) + 1 script de escenario nuevo. El BFF y Operaciones no cambian.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Cumplimiento | Evidencia |
|---|---|---|
| **I — Comunicación solo por eventos** | PASA | Los cuatro servicios de dominio siguen sin clientes HTTP entre sí; toda comunicación nueva de la saga viaja por los tres tópicos existentes. `saga_log` solo expone HTTP hacia el BFF (igual que los otros cuatro), nunca llama hacia adentro |
| **II — Contratos con esquema y evolución compatible** | PASA (con verificación pendiente en Fase 1) | Todos los campos nuevos son `Tipo(default=..., required_default=True)`, agregados al final; ningún campo cambia de tipo/significado; sin enumeraciones Avro cerradas; el sobre de 8 campos se repite explícito en cada `Record`. `herramientas/verificar_contratos.py` se extiende para cubrir los dos contratos tocados |
| **III — Capas separadas y servicios autónomos** | PASA | `saga_log` nace copiando `servicios/_plantilla/` completa (Dockerfile, seedwork, `correlacion.py` idéntico); los cambios en GT/EMP/ACR respetan su propia separación dominio/aplicación/infraestructura existente; ningún dominio importa infraestructura ajena |
| **IV — Comportamiento cambiable por datos, no por código** | N/A | Esta historia no introduce reglas regionales ni de ciclo de vida nuevas condicionadas por país; usa las regiones y el ciclo de vida que ya existen |
| **V — Resiliencia por diseño: al-menos-una-vez e idempotencia** | PASA (diseño explícito) | Reserva de proveedor vía restricción de unicidad + `IntegrityError` (no un `SELECT` previo); `saga_log` deduplica por `mensaje_id` único; todas las suscripciones nuevas se pre-crean en `infra/pulsar/inicializar.sh`/`comun.sh` antes de levantar tráfico; ningún handler nuevo reintenta dentro de un paso (Assumptions del spec) |
| **VI — Verificación honesta** | PASA (diseño explícito) | `escenarios/saga.sh` relee del broker/DB lo que produjo cada caso, compara contra literales (`ASIGNADO`, `CANCELADO`, número de pasos), y reporta PASA/FALLA por criterio en `docs/resultados/` |

Ninguna violación que requiera `Complexity Tracking` formal. Una complejidad aceptada y ya
documentada por el propio negocio (R5-1 del US-01): la nueva suscripción de Gestión de Trabajos
sobre `evt-acreditacion` recibe también el tráfico masivo de `AcreditacionActualizada` del
escenario de escalabilidad; se mitiga descartando por `type` antes de cualquier lógica de negocio,
mismo patrón que ya usa la proyección de Emparejamiento hoy — no es una complejidad nueva de
arquitectura, es un costo de tráfico ya aceptado en el diseño de negocio.

## Project Structure

### Documentation (this feature)

```text
specs/002-saga-asignacion-trabajo/
├── plan.md              # This file
├── research.md          # Fase 0 — 10 decisiones técnicas (D1–D10)
├── data-model.md        # Fase 1 — entidades por servicio
├── quickstart.md         # Fase 1 — guía de validación de los 4 casos
├── contracts/            # Fase 1 — contratos de mensajería y API HTTP nueva
│   ├── evt-emparejamiento.md
│   ├── evt-acreditacion.md
│   ├── cmd-trabajo.md
│   └── saga-log-api.md
└── tasks.md              # Fase 2 (/speckit-tasks, no se crea aquí)
```

### Source Code (repository root)

Repositorio de microservicios existente — no aplica ninguna de las plantillas de opción única del
generador. Estructura real, con lo que esta historia toca marcado:

```text
servicios/
├── _plantilla/                        # sin cambios; es la base que copia saga_log
├── gestion_trabajos/src/gestion_trabajos/
│   ├── modulos/trabajos/
│   │   ├── dominio/entidades.py        # MOD: + Trabajo.proveedor_id, + transición CREADO→EMPAREJANDO
│   │   ├── aplicacion/comandos/        # + comandos que atienden vigencia-confirmada / vigencia-rechazada / sin-candidatos
│   │   ├── infraestructura/consumidores.py   # + 2 suscripciones nuevas (evt-emparejamiento, evt-acreditacion)
│   │   ├── infraestructura/dto.py      # MOD: + columna trabajos.proveedor_id
│   │   └── infraestructura/schema/v1/  # copias locales actualizadas de evt_emparejamiento.py / evt_acreditacion.py
│   └── consumidor.py                   # + hilos para las suscripciones nuevas
├── emparejamiento/src/emparejamiento/
│   ├── modulos/emparejamiento/
│   │   ├── dominio/entidades.py        # MOD: + Emparejamiento.proveedor_reservado
│   │   ├── dominio/repositorios.py     # + RepositorioReservasProveedor
│   │   ├── aplicacion/comandos/        # + reservar/liberar
│   │   ├── infraestructura/consumidores.py   # + suscripción emparejamiento-saga (evt-acreditacion)
│   │   ├── infraestructura/dto.py      # + tabla reservas_proveedor
│   │   └── infraestructura/schema/v1/  # evt_emparejamiento.py extendido, evt_acreditacion.py extendido
│   └── consumidor.py                   # ROL_CONSUMIDOR gana un tercer rol o el regional absorbe la nueva suscripción
├── acreditacion/src/acreditacion/
│   ├── modulos/acreditacion/
│   │   ├── aplicacion/comandos/        # + confirmar/rechazar vigencia
│   │   ├── infraestructura/consumidores.py   # + suscripción acreditacion (evt-emparejamiento)
│   │   ├── infraestructura/dto.py      # + tabla vigencia_por_proveedor
│   │   ├── infraestructura/repositorios.py   # + upsert de la proyección junto al event store
│   │   └── infraestructura/schema/v1/  # evt_emparejamiento.py (copia local), evt_acreditacion.py extendido
│   └── consumidor.py                   # + hilo para la suscripción nueva
├── saga_log/                            # NUEVO — copia de _plantilla
│   ├── Dockerfile, requirements.txt
│   └── src/saga_log/
│       ├── api/sagas.py                 # GET /sagas/{trabajo_id}, /sagas, /sagas/resumen
│       ├── consumidor.py                 # 3 hilos: evt-trabajo-.*, evt-emparejamiento, evt-acreditacion
│       ├── modulos/sagas/
│       │   ├── aplicacion/{comandos,queries}/
│       │   └── infraestructura/{consumidores,dto,repositorios}.py
│       └── seedwork/                    # copiado tal cual de _plantilla (correlacion.py incluido)
├── bff/                                  # SIN CAMBIOS — ya cableado (URL_SAGAS, /sagas/*, /trabajos/asignacion)
└── operaciones/                          # SIN CAMBIOS

contratos/v1/
├── evt_emparejamiento.py                # MOD: + proveedor_id, + motivo, + 2 constantes TIPO_*
└── evt_acreditacion.py                  # MOD: + trabajo_id, + categoria, + 2 constantes TIPO_*

infra/pulsar/
├── topologia.env                        # sin cambios (no hay región/namespace nuevo)
├── comun.sh                              # MOD: crear_region() sin cambios; nuevas suscripciones no-regionales se agregan en inicializar.sh
└── inicializar.sh                        # MOD: + 5 suscripciones nuevas (ver research.md D6)

docker-compose.yml                        # MOD: + postgres-saga, + saga-log, + saga-log-consumidor, + red-saga (red-bff-saga ya existía)

herramientas/verificar_contratos.py       # MOD: cubre los 2 contratos extendidos

escenarios/
└── saga.sh                               # NUEVO — los 4 casos, patrón de mod-3.sh/escenario-8.sh

postman/hogar-alpes-bff.postman_collection.json   # SIN CAMBIOS DE CONTENIDO — carpetas 5 y 7 ya existen, pasan a verde
```

**Structure Decision**: cada servicio mantiene su propia separación dominio/aplicación/infraestructura
(Principio III); el servicio nuevo nace copiando `_plantilla/` en lugar de generarse o compartir
código con los demás (mismo costo de duplicación ya aceptado en `TO-7`). No se introduce ningún
directorio de nivel superior nuevo (`src/`, `backend/`, etc.) porque el repositorio ya es
multi-servicio.

## Complexity Tracking

*Sin violaciones que requieran justificación además de la ya registrada en la tabla de
Constitution Check (R5-1, tráfico aceptado, no arquitectura nueva).*
