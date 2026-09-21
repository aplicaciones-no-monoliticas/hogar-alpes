---

description: "Task list template for feature implementation"
---

# Tasks: Despliegue del sistema en Kubernetes sobre AWS

**Input**: Design documents from `/specs/003-despliegue-kubernetes-aws/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: No se pidieron pruebas automatizadas de tipo unit/contract-test tradicionales (esta
es una historia de infraestructura). La verificación honesta que exige la constitución
(Principio VI) se cumple con los guiones de `escenarios/*-k8s.sh` y la ejecución real de
`quickstart.md`, que sí aparecen como tareas explícitas dentro de cada historia.

**Organization**: Tareas agrupadas por historia de usuario (spec.md), en el mismo orden de
prioridad y con el mismo orden de trabajo de riesgo-primero que ya definió el documento de
negocio (Pulsar persistente antes que nada).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Se puede ejecutar en paralelo (archivos distintos, sin dependencia de una tarea sin
  terminar)
- **[Story]**: A qué historia de usuario pertenece (US1..US5)
- Cada tarea incluye la ruta de archivo exacta

## Path Conventions

Extensión de infraestructura sobre el monorepo existente — todo bajo `infra/`, `escenarios/`,
`docs/` y `README.md` de la raíz, según `plan.md` §Project Structure. No se toca `servicios/*`
ni `contratos/*`.

---

## Phase 1: Setup

**Purpose**: Preparar el árbol de directorios y confirmar que la cuenta de AWS permite lo que la
historia necesita, antes de escribir cualquier manifiesto (R5-13, orden de trabajo paso 1).

- [X] T001 Crear el árbol vacío `infra/aws/terraform-eks/` y `infra/k8s/{pulsar,bases-de-datos,servicios,configuracion,red,entornos}/` según `plan.md` §Project Structure
- [X] T002 Verificar qué permite la cuenta de AWS del curso (tipos de instancia EKS disponibles, límite de nodos, si EKS/EBS CSI/ECR están habilitados) y anotar el resultado en `docs/decisiones.md`; si algo no se permite, registrar la limitación y su alternativa (CA-3.29, FR-025)
- [X] T003 [P] Crear los seis repositorios ECR (`hogar-alpes/gestion-trabajos`, `hogar-alpes/operaciones`, `hogar-alpes/acreditacion`, `hogar-alpes/emparejamiento`, `hogar-alpes/saga-log`, `hogar-alpes/bff`) en `infra/aws/terraform-eks/ecr.tf`
- [X] T004 [P] Escribir `infra/k8s/publicar-imagenes.sh`: construye los seis `Dockerfile` existentes sin modificarlos, etiqueta cada imagen con `git rev-parse --short HEAD` (nunca `latest`, FR-004/R5-15) y hace `docker push` a su repositorio ECR

**Checkpoint**: repositorios ECR existentes y guion de publicación listo; no depende de que el clúster exista todavía.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: El clúster EKS, su capacidad de aplicar `NetworkPolicy`, su almacenamiento
persistente y la configuración/secretos compartidos — nada de las historias de usuario puede
desplegarse sin esto.

**⚠️ CRITICAL**: Ninguna tarea de US1-US5 puede empezar hasta que esta fase termine.

- [X] T005 Escribir `infra/aws/terraform-eks/main.tf`: VPC dedicada nueva (no reutiliza la `10.42.0.0/16` de `infra/aws/terraform/main.tf`), clúster EKS y node group administrado, siguiendo el mismo patrón de `data "aws_ec2_instance_type_offerings"` + `lifecycle.ignore_changes` ya usado en `infra/aws/terraform/main.tf` para evitar reemplazos por zona inestable
- [X] T006 [P] Escribir `infra/aws/terraform-eks/variables.tf` (`region`, `instance_type` con mismo patrón de fallback que la EC2 existente, `ssh_cidr` si aplica bastión, `node_count`)
- [X] T007 [P] Escribir `infra/aws/terraform-eks/outputs.tf` (`cluster_name`, `cluster_endpoint`, comando `aws eks update-kubeconfig` listo para copiar)
- [X] T008 Habilitar en `infra/aws/terraform-eks/main.tf` los add-ons de EKS: VPC CNI (por defecto), EBS CSI driver (`aws_eks_addon`), y aplicar los manifiestos oficiales de Calico en modo *policy-only* (research.md Decisión 2) — sin esto ningún `NetworkPolicy` de US2 tiene efecto (R5-12)
- [X] T009 [P] Crear el `StorageClass` `gp3` en `infra/k8s/entornos/storageclass.yaml` (`provisioner: ebs.csi.aws.com`)
- [X] T010 [P] Crear `infra/k8s/configuracion/reglas-regionales-configmap.yaml` a partir del contenido actual de `infra/sidecar/reglas_regionales.json` (FR-017; la fuente en `infra/sidecar/` no se borra, sigue siendo la usada por Compose)
- [X] T011 [P] Crear `infra/k8s/configuracion/variables-comunes-configmap.yaml` con host/puerto de Pulsar, nombres de tópicos y nivel de log ya declarados como variables de entorno en `docker-compose.yml`
- [X] T012 Escribir `infra/k8s/generar-secretos.sh`: genera una contraseña aleatoria distinta por cada una de las 5 instancias de PostgreSQL y las aplica como `Secret` de Kubernetes (`kubectl create secret generic ... --from-literal=`), sin escribir ningún valor en un archivo versionado (FR-012, CA-3.15)
- [X] T013 Configurar `infra/k8s/entornos/` con `kustomize`: una base común y dos overlays, `reducido/` y `completo/` (menos copias y menos particiones en `reducido/`), según research.md Decisión 1
- [X] T014 Escribir `infra/k8s/desplegar.sh` (esqueleto de orquestación, aún sin los manifiestos de las historias): aplica en el orden fijado por `contracts/comandos-despliegue.md` — `red/` → `configuracion/` → secretos → `bases-de-datos/` → `pulsar/` (espera *readiness* de brokers) → `Job` de init → `servicios/` (API antes que consumidor) → `bff/`; acepta `[reducido|completo]` como argumento; debe ser idempotente
- [X] T015 Escribir `infra/k8s/destruir.sh`: `kubectl delete -k` sobre lo aplicado por `desplegar.sh`

**Checkpoint**: clúster desplegable, con `NetworkPolicy` capaz de aplicarse, almacenamiento persistente disponible y configuración/secretos resueltos. Las historias de usuario pueden empezar.

---

## Phase 3: User Story 1 - Desplegar el sistema completo en Kubernetes desde cero (Priority: P1) 🎯 MVP

**Goal**: Los seis servicios, las cinco bases de datos y el clúster de Pulsar quedan
desplegados y sanos dentro de EKS, con el BFF accesible desde fuera por una única dirección y la
colección de Postman corriendo en verde contra ella.

**Independent Test**: Desde una cuenta de AWS limpia, seguir `quickstart.md` pasos 1-5; el
sistema completo queda funcionando y la colección de Postman pasa en verde.

### Implementation for User Story 1

- [X] T016 [P] [US1] Crear `infra/k8s/bases-de-datos/postgres-trabajos.yaml` (`StatefulSet` + `Service` headless + `PersistentVolumeClaim` sobre `gp3`, credenciales desde el `Secret` de T012)
- [X] T017 [P] [US1] Crear `infra/k8s/bases-de-datos/postgres-operaciones.yaml` (mismo patrón que T016)
- [X] T018 [P] [US1] Crear `infra/k8s/bases-de-datos/postgres-acreditacion.yaml` (mismo patrón que T016)
- [X] T019 [P] [US1] Crear `infra/k8s/bases-de-datos/postgres-emparejamiento.yaml` (mismo patrón que T016)
- [X] T020 [P] [US1] Crear `infra/k8s/bases-de-datos/postgres-saga.yaml` (mismo patrón que T016)
- [X] T021 [US1] Crear `infra/k8s/pulsar/zookeeper.yaml` (`StatefulSet` 1 réplica + `Service` + `PersistentVolumeClaim` sobre `gp3`)
- [X] T022 [US1] Crear `infra/k8s/pulsar/bookies.yaml` (`StatefulSet` 2 réplicas + `Service` headless + `PersistentVolumeClaim` sobre `gp3`; depende de T021)
- [X] T023 [US1] Crear `infra/k8s/pulsar/brokers.yaml` (`Deployment` 2 réplicas, sin `PersistentVolumeClaim` — no persisten datos — + `Service`; depende de T022)
- [X] T024 [US1] Crear `infra/k8s/pulsar/job-init.yaml`: `Job` que reutiliza `infra/pulsar/inicializar.sh` tal cual (sin reescribirlo), con precondición de esperar el `readinessProbe` de los brokers de T023 (research.md Decisión 5)
- [X] T025 [P] [US1] Crear `infra/k8s/servicios/gestion-trabajos.yaml` (`Deployment` API 2 copias + `Service` + `Deployment` consumidor 1 copia, imagen `hogar-alpes/gestion-trabajos:<tag>` de ECR, monta el `ConfigMap` `reglas-regionales` de T010)
- [X] T026 [P] [US1] Crear `infra/k8s/servicios/operaciones.yaml` (`Deployment` API 1 copia + `Service` + `Deployment` consumidor 1 copia)
- [X] T027 [P] [US1] Crear `infra/k8s/servicios/acreditacion.yaml` (`Deployment` API 1 copia + `Service` + `Deployment` consumidor 1 copia)
- [X] T028 [P] [US1] Crear `infra/k8s/servicios/emparejamiento.yaml` (`Deployment` API 2 copias + `Service` + `Deployment` consumidor de proyección 1 copia + `Deployment` consumidor regional andina 1 copia + `Deployment` consumidor regional norteamérica 1 copia)
- [X] T029 [P] [US1] Crear `infra/k8s/servicios/saga-log.yaml` (`Deployment` API 1 copia + `Service` + `Deployment` consumidor 1 copia)
- [X] T030 [US1] Crear `infra/k8s/servicios/bff.yaml` (`Deployment` 2 copias + `Service` tipo `LoadBalancer`, único expuesto hacia afuera — FR-005)
- [X] T031 [US1] Completar `infra/k8s/desplegar.sh` (iniciado en T014) referenciando los manifiestos de T016-T030 en el orden ya fijado, y `infra/k8s/destruir.sh` (T015) para que cubran todos los recursos nuevos
- [X] T032 [US1] Agregar un entorno nuevo a la colección Postman `postman/hogar-alpes-bff.postman_collection.json` (o archivo de entorno hermano) que apunte a la URL del `Service` `LoadBalancer` del BFF, cambiando solo el entorno (CA-3.4)
- [X] T033 [US1] Ejecutar `quickstart.md` pasos 1-5 contra una cuenta de AWS real: crear el clúster, publicar imágenes, desplegar, verificar salud de los 6 servicios/5 bases/Pulsar, correr la colección de Postman en verde; registrar el resultado en `docs/resultados/despliegue-k8s.md`

**Checkpoint**: el sistema completo está desplegado, sano, y accesible por el BFF — MVP demostrable.

---

## Phase 4: User Story 2 - Conservar el aislamiento de red entre servicios (Priority: P1)

**Goal**: Ningún servicio de dominio puede alcanzar la base de datos ni la API de otro servicio
de dominio; solo el BFF los alcanza a los seis; nada queda expuesto a internet salvo el BFF.

**Independent Test**: Con el sistema de US1 ya desplegado, correr `escenarios/red-k8s.sh` y
confirmar que las nueve conexiones prohibidas entre bases de datos, las conexiones HTTP entre
servicios de dominio, y el acceso externo directo a bases/Pulsar, todas fallan.

### Implementation for User Story 2

- [X] T034 [P] [US2] Crear `infra/k8s/red/deny-default-db.yaml`: `NetworkPolicy` tipo *default-deny* de ingreso para cada `postgres-*` (data-model.md §Reglas de red)
- [X] T035 [P] [US2] Crear `infra/k8s/red/allow-db-owners.yaml`: cinco reglas `NetworkPolicy` de excepción, una por base, que permiten ingreso solo desde los pods del servicio dueño (`app=gestion-trabajos-api`/`-consumidor` → `postgres-trabajos`, y así para las otras cuatro)
- [X] T036 [P] [US2] Crear `infra/k8s/red/deny-default-api.yaml`: `NetworkPolicy` tipo *default-deny* de ingreso para cada `Service` `*-api` de los seis servicios de dominio
- [X] T037 [P] [US2] Crear `infra/k8s/red/allow-bff.yaml`: `NetworkPolicy` que permite ingreso a cada `*-api` únicamente desde pods con `app=bff`
- [X] T038 [US2] Confirmar en `infra/k8s/desplegar.sh` (T031) que `red/` se aplica primero, antes que cualquier carga de trabajo (contracts/comandos-despliegue.md)
- [X] T039 [US2] Escribir `escenarios/red-k8s.sh` implementando exactamente las comprobaciones de `contracts/politicas-red.md`: las nueve conexiones TCP prohibidas entre servicio y base ajena, las conexiones HTTP prohibidas entre servicios de dominio, la comprobación positiva de control (BFF → los seis `/health`), y el intento de acceso externo directo a una base/Pulsar; reporta cada una como PASA/FALLA
- [X] T040 [US2] Ejecutar `escenarios/red-k8s.sh` contra el clúster desplegado y registrar el resultado en `docs/resultados/red-k8s.md` (CA-3.11 a CA-3.14)

**Checkpoint**: el aislamiento de red de Compose queda reproducido y verificado en Kubernetes — el sistema deja de ser "arquitectónicamente más débil" (R5-12 cerrado).

---

## Phase 5: User Story 3 - Persistencia y auto-recuperación ante fallas (Priority: P1)

**Goal**: Si se elimina el proceso de un servicio, una base de datos o un bookie de Pulsar, el
clúster lo recupera solo, sin pérdida de datos ni de posición de lectura.

**Independent Test**: Con el sistema de US1 desplegado, eliminar un pod de cada tipo
(servicio, base de datos, bookie) y confirmar que cada uno vuelve, conserva su estado, y el
sistema sigue respondiendo.

### Implementation for User Story 3

- [X] T041 [P] [US3] Agregar `readinessProbe`/`livenessProbe` `httpGet: /health` a los seis `Deployment` de API creados en US1 (`infra/k8s/servicios/*.yaml`) — el endpoint ya existe en cada servicio (Restricciones Técnicas de la constitución)
- [X] T042 [P] [US3] Definir y agregar la comprobación de salud distinta para los `Deployment` consumidor (sin API HTTP) en `infra/k8s/servicios/*.yaml`, según el contrato de `contracts/comandos-despliegue.md` §Comprobación de salud (R5-16): probe `exec` que verifica que el proceso sigue conectado al broker
- [X] T043 [US3] Agregar `readinessProbe` `exec: pg_isready` a los cinco `StatefulSet` de PostgreSQL (`infra/k8s/bases-de-datos/*.yaml`, creados en T016-T020)
- [X] T044 [US3] Confirmar `storageClassName: gp3` y una política de retención de volumen adecuada (`persistentVolumeReclaimPolicy` no `Delete` prematuro) en los `StatefulSet` de PostgreSQL, ZooKeeper y bookies (T016-T022) — ninguno debe escribir en la capa del contenedor (FR-016)
- [X] T045 [US3] Escribir `escenarios/recuperacion-k8s.sh`: elimina un pod de un servicio (confirma que vuelve y responde), elimina un pod de PostgreSQL (confirma que un dato conocido sigue presente al volver), elimina un pod bookie (confirma que los mensajes ya publicados y la posición de una suscripción conocida se conservan vía `pulsar-admin`)
- [X] T046 [US3] Ejecutar `escenarios/recuperacion-k8s.sh` contra el clúster desplegado y registrar el resultado en `docs/resultados/recuperacion-k8s.md` (CA-3.16 a CA-3.19)

**Checkpoint**: las tres historias P1 (US1-US3) están completas — el sistema en Kubernetes cumple la promesa central de disponibilidad que motivó la historia.

---

## Phase 6: User Story 4 - Los escenarios de calidad de la Entrega 4 funcionan igual en Kubernetes (Priority: P2)

**Goal**: Los cinco escenarios de calidad ya demostrados en Compose (disponibilidad,
escalabilidad, región nueva, país nuevo, adaptador de persistencia) y la saga completa producen
resultados comparables en Kubernetes, reportados por separado.

**Independent Test**: Ejecutar cada guion `escenarios/*-k8s.sh` contra el sistema desplegado y
comparar su resultado con el ya documentado para Compose; cualquier diferencia queda explicada
por escrito, nunca escondida.

### Implementation for User Story 4

- [X] T047 [P] [US4] Escribir `escenarios/disponibilidad-k8s.sh`: baja a cero las copias del `Deployment` consumidor de Operaciones (`kubectl scale --replicas=0`), confirma que el acumulado de mensajes pendientes crece sin afectar a Gestión de Trabajos, lo vuelve a levantar y confirma 100% procesado sin duplicar (CA-3.20)
- [X] T048 [P] [US4] Escribir `escenarios/escalabilidad-k8s.sh`: duplica las copias de un `Deployment` consumidor (`kubectl scale`) y mide el aumento de velocidad de procesamiento con el mismo método que usa el escenario ya existente de Compose (CA-3.21)
- [X] T049 [P] [US4] Escribir `escenarios/region-nueva-k8s.sh`: corre `infra/pulsar/agregar-region.sh` como tarea contra el clúster (vía `kubectl exec` sobre un pod administrativo o un `Job` puntual) y despliega el `Deployment` del consumidor de la nueva región, confirmando que las regiones activas no se interrumpen (CA-3.22)
- [X] T050 [P] [US4] Escribir `escenarios/pais-nuevo-k8s.sh`: edita `infra/k8s/configuracion/reglas-regionales-configmap.yaml` (T010) agregando un país, aplica el cambio y hace `kubectl rollout restart` únicamente del `Deployment` de Gestión de Trabajos, confirmando 0 archivos de código modificados y 0 imágenes reconstruidas (CA-3.23)
- [X] T051 [P] [US4] Escribir `escenarios/adaptador-persistencia-k8s.sh`: cambia la variable de entorno del adaptador de persistencia de Gestión de Trabajos en su manifiesto y hace `kubectl rollout restart`, confirmando comportamiento equivalente al de Compose (CA-3.24)
- [X] T052 [US4] Ejecutar los cinco guiones T047-T051 contra el clúster desplegado y registrar cada resultado en su propio archivo bajo `docs/resultados/` (p. ej. `disponibilidad-k8s.md`), identificado como corrido en Kubernetes y sin mezclarse con las tablas ya existentes de Compose (SC-006)
- [X] T053 [US4] Verificar la saga de asignación de trabajo contra el BFF desplegado en Kubernetes: caso exitoso y los tres casos de fallo con su compensación completa, reutilizando el guion/colección ya existente de la saga apuntado al entorno de Kubernetes (FR-019, CA-3.10)
- [X] T054 [US4] Verificar la trazabilidad por identificador de correlación entre pods: documentar en `infra/k8s/README.md` el comando para consultar los registros de varios procesos a la vez (p. ej. `kubectl logs -l ... --prefix`) y confirmar que buscar un `correlation_id` conocido devuelve la cadena completa (FR-020, CA-3.10b)

**Checkpoint**: toda la evidencia de calidad de la Entrega 4 queda reproducida y documentada para el nuevo entorno.

---

## Phase 7: User Story 5 - Convivencia con el despliegue existente en Docker Compose (Priority: P1)

**Goal**: `docker compose up` sigue levantando el sistema completo exactamente igual que antes de
esta historia; la documentación explica cuándo usar cada camino.

**Independent Test**: En un checkout limpio con todos los cambios de esta historia, correr el
comando de arranque de Docker Compose y confirmar que el sistema se levanta igual que antes.

### Implementation for User Story 5

- [X] T055 [US5] Correr `docker compose up -d --build` en un checkout limpio tras todos los cambios de esta historia y repetir la verificación de salud básica ya usada en la Entrega 4; confirmar 0 diferencias (CA-3.8, criterio duro)
- [X] T056 [US5] Actualizar `README.md` de la raíz explicando que existen dos formas de desplegar (Docker Compose y Kubernetes/EKS) y en qué situación conviene cada una (FR-024, CA-3.28)

**Checkpoint**: las tres formas de despliegue (Compose local, EC2, y ahora Kubernetes) coexisten sin que ninguna rompa a las otras.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Cerrar los criterios de documentación, costo y verificación final que dependen de
que todas las historias anteriores ya estén completas.

- [X] T057 [P] Completar `infra/k8s/README.md` con el procedimiento íntegro: requisitos previos, creación del clúster, publicación de imágenes, despliegue, verificación y destrucción, con los comandos exactos (CA-3.26)
- [X] T058 [P] Documentar en `infra/k8s/README.md` el costo aproximado por hora y por día del clúster desplegado, y cómo dejar de pagar cuando no se usa (CA-3.27, FR-023)
- [X] T059 [P] Revisar y consolidar en `infra/k8s/README.md` cualquier limitación de la cuenta de AWS encontrada durante T002 y su alternativa adoptada (CA-3.29, FR-025)
- [X] T060 Verificar que el repositorio no contiene ninguna credencial, dirección de cuenta de AWS real ni dato del clúster real (`git grep` sobre patrones de secreto/ARN/IP antes de cualquier commit final) (FR-012, CA-3.15)
- [X] T061 Registrar en `docs/decisiones.md` las decisiones y tropiezos de la implementación (incluida la activación o no del plan alterno de Pulsar, research.md Decisión 3) con el mismo estilo honesto del resto del documento
- [ ] T062 [P] Registrar en `docs/actividades.md` quién hizo qué, con enlaces a sus commits y a su pull request
- [X] T063 Ejecutar `quickstart.md` de punta a punta como si fuera alguien que no participó en la historia, confirmando que los treinta criterios de aceptación de `spec.md` quedan cumplidos o documentados como limitación (CA-3.1, Definición de terminado)
- [X] T064 Destruir el clúster tras la verificación final (`infra/k8s/destruir.sh` + `terraform destroy` en `infra/aws/terraform-eks/`) y confirmar que no queda ningún recurso de AWS cobrando (Definición de terminado)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias — puede empezar de inmediato
- **Foundational (Phase 2)**: depende de Setup — BLOQUEA las cinco historias de usuario
- **User Story 1 (Phase 3)**: depende solo de Foundational — es el MVP
- **User Story 2 (Phase 4)**: depende de Foundational **y** de que US1 exista desplegado (necesita los `Service`/`Deployment` de US1 como destino de las políticas) — no puede verificarse sin el sistema de US1 corriendo
- **User Story 3 (Phase 5)**: depende de Foundational y de los manifiestos de US1 (agrega probes/reclaim-policy sobre los mismos archivos) — puede implementarse en paralelo con US2 una vez US1 está desplegado, ambas tocan archivos distintos salvo T038/T041 que son ediciones menores sobre los mismos YAML de US1 (secuenciar si un mismo desarrollador toca ambos)
- **User Story 4 (Phase 6)**: depende de que US1, US2 y US3 ya estén verificadas (usa el sistema completo, con red restringida y recuperación probada, como base de cada escenario)
- **User Story 5 (Phase 7)**: independiente de las demás en implementación (solo toca `docker-compose.yml`-adyacentes por *no* tocarlo, y `README.md`); se recomienda ejecutarla al final para confirmar que ningún cambio de infraestructura de las fases anteriores la rompió
- **Polish (Phase 8)**: depende de que todas las historias deseadas estén completas

### Within Each User Story

- Bases de datos y componentes de Pulsar antes que los servicios que dependen de ellos (US1)
- Reglas *default-deny* antes que las reglas de excepción, y ambas antes de correr el guion de verificación (US2)
- Probes y reclaim policy antes del guion de recuperación (US3)
- Los cinco guiones de escenario antes de su ejecución consolidada (US4)

### Parallel Opportunities

- Todas las tareas de Setup marcadas [P] (T003, T004)
- Dentro de Foundational: T006, T007, T009, T010, T011 en paralelo entre sí
- Dentro de US1: T016-T020 (las cinco bases) en paralelo; T025-T029 (los cinco servicios de dominio) en paralelo, después de que T021-T024 (Pulsar) estén listos
- Dentro de US2: T034-T037 (las cuatro familias de `NetworkPolicy`) en paralelo
- Dentro de US4: T047-T051 (los cinco guiones de escenario) en paralelo entre sí
- US2 y US3 pueden trabajarse en paralelo por personas distintas una vez US1 está desplegado

---

## Parallel Example: User Story 1

```bash
# Lanzar las cinco bases de datos juntas:
Task: "Crear infra/k8s/bases-de-datos/postgres-trabajos.yaml"
Task: "Crear infra/k8s/bases-de-datos/postgres-operaciones.yaml"
Task: "Crear infra/k8s/bases-de-datos/postgres-acreditacion.yaml"
Task: "Crear infra/k8s/bases-de-datos/postgres-emparejamiento.yaml"
Task: "Crear infra/k8s/bases-de-datos/postgres-saga.yaml"

# Una vez Pulsar (T021-T024) está listo, lanzar los cinco servicios de dominio juntos:
Task: "Crear infra/k8s/servicios/gestion-trabajos.yaml"
Task: "Crear infra/k8s/servicios/operaciones.yaml"
Task: "Crear infra/k8s/servicios/acreditacion.yaml"
Task: "Crear infra/k8s/servicios/emparejamiento.yaml"
Task: "Crear infra/k8s/servicios/saga-log.yaml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup
2. Completar Phase 2: Foundational (CRÍTICO — bloquea todas las historias)
3. Completar Phase 3: User Story 1
4. **DETENERSE Y VALIDAR**: correr `quickstart.md` pasos 1-5 de forma independiente
5. Demostrar el sistema desplegado, sano y accesible por el BFF

### Incremental Delivery

1. Setup + Foundational → clúster listo
2. US1 → sistema completo desplegado y accesible (MVP demostrable)
3. US2 → aislamiento de red verificado (cierra el riesgo R5-12)
4. US3 → persistencia y auto-recuperación verificadas (cierra la promesa central de disponibilidad)
5. US4 → evidencia de calidad de la Entrega 4 reproducida en el entorno nuevo
6. US5 → confirmación final de que Compose sigue intacto
7. Polish → documentación, costo, limpieza de recursos

### Riesgo primero (orden de trabajo del documento de negocio)

Aunque las historias están priorizadas P1/P1/P1/P2/P1 por valor de negocio, dentro de
Foundational y US1 el trabajo real debe atacar primero Pulsar con almacenamiento persistente
(T021-T024, R5-11) antes que las bases de datos o los servicios — si a las ~4 horas no converge,
activar el plan alterno de `research.md` Decisión 3 (reducir a 1 broker + 1 bookie) y
documentarlo, en vez de bloquear el resto de la historia.

---

## Notes

- [P] = archivos distintos, sin dependencia entre sí
- [Story] mapea cada tarea a su historia de usuario para trazabilidad
- Cada historia debe quedar completable y verificable de forma independiente, salvo las
  dependencias de orden explícitas arriba (US2/US3 necesitan el sistema de US1 corriendo para
  *verificarse*, aunque sus manifiestos se puedan escribir antes)
- Ningún archivo de `servicios/`, `contratos/`, ni `docker-compose.yml` se modifica en ninguna
  tarea de este plan (US5, CA-3.8)
- Confirmar en cada tarea que toca `docs/resultados/` que el resultado se relee del propio
  clúster/broker, nunca se asume porque un comando no protestó (Principio VI)
