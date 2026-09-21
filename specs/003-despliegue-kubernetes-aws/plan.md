# Implementation Plan: Despliegue del sistema en Kubernetes sobre AWS

**Branch**: `003-despliegue-kubernetes-aws` | **Date**: 2026-09-21 | **Spec**: `specs/003-despliegue-kubernetes-aws/spec.md`

**Input**: Feature specification from `/specs/003-despliegue-kubernetes-aws/spec.md`, más el
documento de diseño de negocio ya aprobado
`docs/us-entrega-5/US-03-despliegue-kubernetes-aws.md`.

## Summary

Agregar una tercera forma de desplegar el sistema completo (seis servicios de aplicación, cinco
PostgreSQL y el clúster de Pulsar de tres réplicas ZooKeeper/bookies/brokers) dentro de un
clúster de Kubernetes gestionado (EKS) en AWS, **sin tocar** el `docker-compose.yml` existente ni
la EC2 de `infra/aws/terraform/`. La traducción no es mecánica: hay que declarar explícitamente
en Kubernetes dos garantías que hoy da gratis la topología de redes de Docker Compose —
aislamiento por base de datos (una red por servicio) y "solo el BFF habla HTTP hacia los seis
servicios" — usando `NetworkPolicy` sobre un CNI que las haga cumplir (Calico), y verificarlas
igual que hoy: probando que la conexión prohibida falla, no que la política existe. El
almacenamiento durable de Pulsar (bookies) es el riesgo mayor, ya descartado una vez en la
Entrega 4; se ataca primero con StatefulSets + `PersistentVolumeClaim` sobre `gp3`, con plan
alterno documentado (reducir a 1 bookie/1 broker) si no converge a tiempo. Las imágenes se
publican en Amazon ECR, etiquetadas con el hash corto del commit. El guion de inicialización de
Pulsar (`infra/pulsar/inicializar.sh`) se reutiliza sin reescribir, como un `Job` que corre una
vez. Un segundo Terraform (`infra/aws/terraform-eks/`) crea el clúster EKS de forma independiente
del Terraform de la EC2; los manifiestos de Kubernetes en `infra/k8s/` son la fuente única de lo
que corre adentro, con un solo comando de despliegue y uno de destrucción.

## Technical Context

**Language/Version**: Sin cambios en el código de aplicación — sigue siendo Python 3.11
(`python:3.11-slim`), Principio III de la constitución. Esta historia es puramente de
infraestructura: Terraform (HCL, `>= 1.5`, mismo pin que `infra/aws/terraform/main.tf`) para el
clúster EKS, y manifiestos YAML de Kubernetes (`apiVersion` estable, sin Helm — ver
`research.md` Decisión 1) para lo que corre adentro.

**Primary Dependencies**:
- `hashicorp/aws` ~> 5.0 (ya usado en `infra/aws/terraform/main.tf`) + módulo o recursos nativos
  `aws_eks_cluster`/`aws_eks_node_group` para el clúster.
- CNI con enforcement de `NetworkPolicy`: **Calico** (el complemento nativo de EKS, VPC CNI, no
  aplica `NetworkPolicy` de red entre pods por sí solo sin Calico habilitado — ver
  `research.md` Decisión 2).
- Amazon ECR como registro de contenedores (ya dentro de la misma cuenta de AWS, sin credencial
  nueva que guardar en el repositorio).
- `kubectl` + manifiestos YAML planos, organizados con `kustomize` (ya integrado en `kubectl`,
  sin dependencia nueva) para las diferencias entre entorno reducido y completo (FR de la
  historia "un entorno, con posibilidad de tamaño reducido o completo").
- Operador o manifiestos estáticos de Pulsar: manifiestos estáticos versionados a mano (no un
  operador de terceros) para mantener consistencia con "Se usa un Pulsar propio, no contratado"
  (constitución + spec Assumptions) y no introducir un CRD externo no auditado — ver
  `research.md` Decisión 3.

**Storage**: Las cinco instancias de PostgreSQL y los 2 bookies de Pulsar usan
`PersistentVolumeClaim` respaldados por el `StorageClass` `gp3` de EBS (`ebs.csi.aws.com`, el
driver CSI de EBS debe habilitarse como add-on de EKS). ZooKeeper (1 réplica, igual que Compose)
también usa `PersistentVolumeClaim` para sus metadatos. Ninguna base de datos ni componente de
Pulsar escribe en el `emptyDir` ni en la capa del contenedor (FR-016).

**Testing**: Reutiliza toda la suite existente sin cambios (`pytest` por servicio,
`herramientas/verificar_contratos.py`, la colección Postman
`hogar-alpes-bff.postman_collection.json` con un entorno nuevo apuntando a la URL del `Service`
tipo `LoadBalancer` del BFF). Se agregan: (a) variante Kubernetes de cada guion en `escenarios/`
(mismo nombre + sufijo, ver `research.md` Decisión 4), y (b) un guion nuevo de verificación de
aislamiento de red (`escenarios/red-k8s.sh`) que repite las nueve comprobaciones ya documentadas
para Compose, esta vez ejecutando `kubectl exec` en vez de `docker exec`.

**Target Platform**: Amazon EKS (Kubernetes gestionado) sobre la misma cuenta de AWS educativa ya
usada para la EC2 de Compose; nodos Linux x86_64 en un `node group` administrado.

**Project Type**: Extensión de infraestructura sobre un sistema de microservicios ya existente —
no se toca `servicios/*` ni `contratos/*`; todo el trabajo vive bajo `infra/`. No aplica ninguna
plantilla de "single project"/"web application"; ver Project Structure abajo con la estructura
real ya definida por el documento de negocio (§"Cómo queda organizado en el repositorio").

**Performance Goals**: Sin metas nuevas propias de Kubernetes. Se reutilizan las ya vigentes
(consultas <1s con >100k proveedores; degradación <10% durante una caída; duplicar copias de un
consumidor casi duplica su velocidad) verificándolas en el nuevo entorno — SC-006 del spec exige
reportarlas por separado, nunca mezcladas con las de Compose.

**Constraints**:
- CA-3.8 (FR-021): `docker compose up` MUST seguir funcionando exactamente igual; ningún archivo
  bajo `servicios/`, `contratos/`, ni `docker-compose.yml` se modifica por esta historia.
- FR-008/FR-009/FR-010: el aislamiento de red se declara con `NetworkPolicy` y se verifica
  demostrando que la conexión prohibida falla — no basta con que la política exista (R5-12).
- FR-011/FR-014: ninguna base de datos ni Pulsar tiene `Service` tipo `LoadBalancer` ni
  `NodePort` expuesto; solo el `Service` del BFF es público.
- FR-012: ninguna contraseña ni dato de cuenta real en el repositorio — los `Secret` de
  Kubernetes se generan en el momento del despliegue (script que genera aleatorios y los aplica
  con `kubectl create secret` o `kubectl apply` desde un archivo fuera de git), nunca committeados.
- FR-017: las reglas regionales (`infra/sidecar/reglas_regionales.json`) pasan a `ConfigMap`,
  montado igual que hoy se monta el volumen — cambiar el `ConfigMap` + reiniciar el pod de
  Gestión de Trabajos reproduce el mismo comportamiento que editar el archivo y reiniciar el
  contenedor.
- FR-007: la preparación de tópicos/suscripciones (`infra/pulsar/inicializar.sh`) corre como un
  `Job` de Kubernetes después de que los brokers pasen su *readiness probe*, reutilizando el
  script tal cual (constitución: "no hay que reescribirlo").
- R5-11: Pulsar con almacenamiento persistente es el riesgo mayor y se ataca primero; el plan
  alterno (reducir a 1 bookie) se documenta en `research.md` y se activa solo si a las 4 horas de
  trabajo dedicado no converge.

**Scale/Scope**: ~12 procesos de aplicación (con sus copias, más de 20 pods) + 5 StatefulSets de
PostgreSQL + 1 StatefulSet ZooKeeper + 2 réplicas bookie + 2 réplicas broker + 1 Job de
inicialización + `NetworkPolicy` por servicio (aislamiento DB + aislamiento HTTP) + 2 árboles
Terraform independientes (`terraform/` para la EC2 existente, sin tocar; `terraform-eks/` nuevo)
+ variantes Kubernetes de 5 guiones de escenarios existentes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Cumplimiento | Evidencia |
|---|---|---|
| **I — Comunicación solo por eventos** | PASA | No se toca ningún servicio de dominio; la topología de mensajería (Pulsar) es la misma, solo cambia dónde corren sus procesos. `NetworkPolicy` FR-009 hace la ausencia de HTTP entre servicios de dominio una imposibilidad física en Kubernetes también, igual que las redes separadas de Compose |
| **II — Contratos con esquema y evolución compatible** | N/A | Esta historia no toca `contratos/`; ningún esquema Avro cambia |
| **III — Capas separadas y servicios autónomos** | PASA | Las imágenes que se publican en ECR son las mismas que construye cada `Dockerfile` existente, sin cambios; API y consumidor siguen siendo procesos (`Deployment`) distintos de la misma imagen, nunca un hilo compartido |
| **IV — Comportamiento cambiable por datos, no por código** | PASA (diseño explícito) | `reglas_regionales.json` pasa a `ConfigMap` (FR-017) preservando "agregar país = 0 archivos de código, 0 reconstrucción"; las regiones de Pulsar se siguen creando con `infra/pulsar/comun.sh` `crear_region`, ejecutado ahora vía `kubectl exec`/`Job` en vez de `docker exec` |
| **V — Resiliencia por diseño: al-menos-una-vez e idempotencia** | PASA | Ningún handler cambia; Kubernetes solo agrega recuperación automática de procesos (`Deployment`/`StatefulSet` con reinicio) sobre el mismo diseño idempotente ya existente. Las suscripciones se siguen pre-creando (Job de inicialización) antes de exponer tráfico |
| **VI — Verificación honesta** | PASA (diseño explícito) | Las variantes de `escenarios/*.sh` y el nuevo `red-k8s.sh` releen del clúster (`kubectl get`, consultas a Pulsar admin) igual que hoy releen de Docker/broker; lo que no se pueda ejecutar por límite de la cuenta de AWS se anota como pendiente (FR-025), nunca como hecho |

Ninguna violación que requiera `Complexity Tracking` formal. La complejidad aceptada y ya
declarada por el propio negocio es R5-11 (Pulsar persistente en K8s), con su plan alterno
documentado abajo en `research.md`, no una desviación de la constitución.

## Project Structure

### Documentation (this feature)

```text
specs/003-despliegue-kubernetes-aws/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
infra/
├── aws/
│   ├── terraform/            # YA EXISTE — EC2 + Compose, sin cambios por esta historia
│   └── terraform-eks/        # NUEVO — clúster EKS, node group, add-ons (VPC CNI, EBS CSI, Calico)
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── pulsar/                   # YA EXISTE — inicializar.sh, comun.sh, agregar-region.sh: se
│                              # REUTILIZAN tal cual dentro de infra/k8s/pulsar/job-init.yaml
├── sidecar/                  # YA EXISTE — reglas_regionales.json: se copia como ConfigMap en
│                              # infra/k8s/configuracion/
└── k8s/                       # NUEVO — todo lo que va adentro del clúster
    ├── README.md               # Procedimiento completo (CA-3.26), costo (CA-3.27)
    ├── pulsar/                 # zookeeper.yaml, bookies.yaml, brokers.yaml, job-init.yaml
    ├── bases-de-datos/         # un StatefulSet + Service + PVC por cada una de las 5 bases
    ├── servicios/              # un Deployment (API) + Deployment (consumidor) por servicio,
    │                            # + bff/ (Deployment + Service LoadBalancer)
    ├── configuracion/          # ConfigMap de reglas regionales + ConfigMap de variables comunes
    ├── red/                    # NetworkPolicy: aislamiento por base de datos + "solo BFF → *"
    └── entornos/                # kustomize overlays: reducido/ y completo/

escenarios/
├── *.sh                     # YA EXISTEN — sin cambios (siguen corriendo contra Compose)
└── *-k8s.sh                  # NUEVO — variante Kubernetes de cada uno (FR-018)

docs/
├── us-entrega-5/US-03-despliegue-kubernetes-aws.md   # YA EXISTE — fuente de esta historia
└── resultados/                                        # escenarios en K8s se agregan aquí,
                                                          # identificados como tales (FR-026)
```

**Structure Decision**: Se preserva exactamente el árbol que ya definió el documento de negocio
(§"Cómo queda organizado en el repositorio"): `infra/aws/terraform-eks/` para el clúster,
`infra/k8s/` para todo lo que corre adentro, organizado en los mismos seis subdirectorios que ya
describió la historia. `infra/aws/terraform/` (EC2) y `docker-compose.yml` no se tocan — son un
camino de despliegue paralelo, no reemplazado (CA-3.8).

## Complexity Tracking

*Sin violaciones de la constitución que requieran justificación.*
