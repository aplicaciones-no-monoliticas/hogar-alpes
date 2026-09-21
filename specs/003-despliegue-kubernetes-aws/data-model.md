# Data Model: Despliegue del sistema en Kubernetes sobre AWS

Esta historia no agrega entidades de dominio ni cambia ningún esquema de datos de negocio: es
infraestructura. El "modelo de datos" aquí son los recursos de Kubernetes/AWS que representan los
componentes ya descritos en el spec (Key Entities), con sus campos relevantes y relaciones.

## Clúster de Kubernetes (EKS)

| Campo | Valor / origen |
|---|---|
| Nombre | `hogar-alpes-eks` |
| Región | Misma que `infra/aws/terraform/main.tf` (`var.region`, por defecto `us-east-1`) |
| VPC | Nueva, dedicada (no reutiliza la VPC `10.42.0.0/16` de la EC2 de Compose — clústeres independientes, Assumption del spec) |
| Node group | Administrado, tipo de instancia configurable (`var.instance_type`, mismo patrón de fallback que la EC2 si el tipo no está disponible) |
| Add-ons | VPC CNI (por defecto), EBS CSI driver (PVC), Calico (NetworkPolicy — Decisión 2) |
| Relación | Contiene todos los demás recursos de esta tabla |

## Manifiestos de despliegue (recursos por componente)

| Componente | Tipo de recurso Kubernetes | Copias iniciales | Estado |
|---|---|---|---|
| Gestión de Trabajos — API | `Deployment` + `Service` (ClusterIP) | 2 | Sin estado |
| Gestión de Trabajos — consumidor | `Deployment` | 1 | Sin estado |
| Operaciones — API | `Deployment` + `Service` | 1 | Sin estado |
| Operaciones — consumidor | `Deployment` | 1 | Sin estado |
| Acreditación — API | `Deployment` + `Service` | 1 | Sin estado |
| Acreditación — consumidor | `Deployment` | 1 | Sin estado |
| Emparejamiento — API | `Deployment` + `Service` | 2 | Sin estado |
| Emparejamiento — consumidor de proyección | `Deployment` | 1 | Sin estado |
| Emparejamiento — consumidor por región (andina, norteamérica) | `Deployment` (uno por región) | 1 cada uno | Sin estado |
| Registro de sagas — API | `Deployment` + `Service` | 1 | Sin estado |
| Registro de sagas — consumidor | `Deployment` | 1 | Sin estado |
| BFF | `Deployment` + `Service` tipo `LoadBalancer` | 2 | Sin estado — único expuesto hacia afuera |
| PostgreSQL × 5 | `StatefulSet` + `Service` (headless) + `PersistentVolumeClaim` | 1 cada una | Con estado |
| ZooKeeper | `StatefulSet` + `Service` + `PersistentVolumeClaim` | 1 | Con estado |
| Bookies (Pulsar) | `StatefulSet` + `Service` (headless) + `PersistentVolumeClaim` | 2 | Con estado — el más delicado |
| Brokers (Pulsar) | `Deployment` + `Service` | 2 | Sin estado (los brokers no persisten datos) |
| Preparación de tópicos/tenant | `Job` (`infra/pulsar/inicializar.sh` reutilizado) | 1 (corre una vez) | N/A |

**Relación**: cada `Deployment`/`StatefulSet` de un servicio de dominio referencia, vía variables
de entorno desde un `Secret` (contraseña) y un `ConfigMap` (host/puerto), a exactamente una
instancia de PostgreSQL — la misma relación 1:1 "cada servicio con su propia base" que ya impone
el Principio I de la constitución.

## Registro de contenedores (ECR)

| Campo | Valor |
|---|---|
| Repositorio | Uno por imagen: `hogar-alpes/gestion-trabajos`, `hogar-alpes/operaciones`, `hogar-alpes/acreditacion`, `hogar-alpes/emparejamiento`, `hogar-alpes/saga-log`, `hogar-alpes/bff` (los mismos seis `Dockerfile` ya existentes en `servicios/*/Dockerfile`, sin cambios) |
| Etiqueta | Hash corto del commit (`git rev-parse --short HEAD`) — nunca `latest` (FR-004, mitiga R5-15) |
| Relación | Cada `Deployment` referencia su imagen por repositorio+etiqueta exacta; el procedimiento de verificación (`quickstart.md`) confirma la etiqueta corriendo contra la del commit desplegado |

## Reglas de red (`NetworkPolicy`)

| Regla | Selector origen permitido | Selector destino | Objetivo |
|---|---|---|---|
| Aislamiento por base de datos | Pods del servicio dueño (`app=gestion-trabajos-api` o `app=gestion-trabajos-consumidor`) | `app=postgres-trabajos` puerto 5432 | Solo el dueño de una base la alcanza — igual que la red Docker dedicada de hoy |
| Denegación por defecto entre bases | (ninguno — `NetworkPolicy` vacía tipo *default deny*) | Cada `postgres-*` | Cualquier otro pod queda bloqueado por defecto; la regla de arriba es la única excepción |
| Solo BFF → servicios de dominio | `app=bff` | `app=*-api` (las seis API) puerto correspondiente | Ningún servicio de dominio alcanza a otro por HTTP; solo el BFF llega a los seis |
| Denegación por defecto entre servicios de dominio | (ninguno) | Cada `*-api` | Ningún otro origen (incluidos los propios servicios de dominio entre sí) puede alcanzarlos |
| BFF hacia afuera | `0.0.0.0/0` (vía `Service` `LoadBalancer`) | `app=bff` | Único punto expuesto a internet (FR-011, FR-014) |
| Sin política de ingreso externo | — | `postgres-*`, `zookeeper`, `bookie-*`, `broker-*` | Ningún `Service` de estos componentes es `LoadBalancer`/`NodePort` |

**Relación**: estas políticas son la traducción directa de las "redes" (`red-trabajos`,
`red-bff-trabajos`, etc.) que ya declara `docker-compose.yml` — mismo propósito, mecanismo
distinto (Calico aplicando `NetworkPolicy` en vez de redes Docker aisladas).

## Secretos del clúster

| Campo | Valor |
|---|---|
| Tipo | `Secret` de Kubernetes (`kind: Secret`), generado en el momento del despliegue |
| Contenido | Contraseña de cada una de las 5 instancias de PostgreSQL (aleatoria, distinta por instancia) |
| Origen | Nunca en git; un paso del procedimiento de despliegue genera valores aleatorios y los aplica (`kubectl create secret generic ... --from-literal=` o `kubectl apply -f` sobre un archivo generado y descartado) |
| Relación | Cada `StatefulSet` de PostgreSQL y cada `Deployment` del servicio dueño referencian el mismo `Secret` vía `secretKeyRef` |

## Configuración del clúster (`ConfigMap`)

| ConfigMap | Contenido | Reemplaza |
|---|---|---|
| `reglas-regionales` | Copia de `infra/sidecar/reglas_regionales.json` | El volumen montado en Compose (FR-017) |
| `variables-comunes` | Host/puerto de Pulsar, nombres de tópicos, nivel de log — lo ya declarado como variables de entorno en `docker-compose.yml` | Variables de entorno planas por servicio en Compose |

**Relación**: `gestion-trabajos-api` y `gestion-trabajos-consumidor` montan `reglas-regionales`
como volumen; agregar un país es editar este `ConfigMap` y reiniciar esos dos `Deployment`
(`kubectl rollout restart`), sin tocar ningún otro servicio (FR-017, CA-3.23).
