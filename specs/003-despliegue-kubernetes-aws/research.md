# Research: Despliegue del sistema en Kubernetes sobre AWS

## Decisión 1: Manifiestos YAML planos organizados con `kustomize`, no Helm

**Decision**: Usar manifiestos de Kubernetes estáticos (`apiVersion` estables:
`apps/v1`, `v1`, `networking.k8s.io/v1`, `batch/v1`), organizados con `kustomize` (integrado en
`kubectl` desde 1.14, sin instalar nada nuevo) para las diferencias entre el entorno "reducido" y
el "completo" (menos copias, menos particiones).

**Rationale**: La historia pide "un solo comando" de despliegue y de destrucción (CA-3.6/CA-3.7),
y un procedimiento que otra persona no involucrada pueda seguir literalmente (CA-3.1). Helm
agrega una capa de plantillas (`values.yaml`, funciones de Go template) que oculta el YAML final
detrás de una sintaxis nueva que hay que aprender solo para esta historia; `kustomize` en cambio
edita el mismo YAML declarativo con overlays explícitos (`patchesStrategicMerge`), y ya viene
incluido en `kubectl apply -k`. Coherente con la Constitución (Principio VI: "verificación
honesta" — se prefiere que lo que corre sea literalmente lo que se lee en el archivo).

**Alternatives considered**:
- **Helm**: más popular, pero introduce una dependencia nueva (el binario `helm` o al menos su
  formato de chart) y una capa de indirección que dificulta "seguir el README al pie de la letra"
  para alguien que nunca lo usó. Rechazado por complejidad no justificada por el tamaño del
  proyecto (12 componentes de aplicación).
- **Terraform con el provider de Kubernetes** (`kubernetes_manifest`): mezclaría el ciclo de vida
  del clúster (que cambia poco) con el de las aplicaciones (que cambia en cada iteración),
  haciendo cada `apply` de código innecesariamente lento y arriesgado. Rechazado: se mantiene la
  separación ya usada en el proyecto entre "Terraform crea infraestructura" y "`docker compose` /
  ahora `kubectl` despliega aplicación".

## Decisión 2: Calico como CNI, habilitado sobre el VPC CNI de EKS

**Decision**: Instalar Calico (modo *policy-only*, dejando el enrutamiento de red al VPC CNI de
Amazon, que EKS trae por defecto) como el componente que hace cumplir los `NetworkPolicy`.

**Rationale**: El VPC CNI por defecto de EKS asigna IPs de la VPC a los pods pero **no aplica**
objetos `NetworkPolicy` de Kubernetes — sin un componente adicional, cualquier pod puede alcanzar
cualquier otro, exactamente el riesgo R5-12 que la historia identifica como el más fácil de pasar
por alto. Calico es el complemento oficialmente soportado por AWS para esto (documentado como
add-on de EKS), no requiere reemplazar el CNI de red (menor riesgo que Cilium en modo reemplazo
completo), y es lo que permite que CA-3.13 se pueda verificar de verdad: sin él, las políticas se
declaran pero no se aplican ("el peor de los dos mundos", como dice el documento de negocio).

**Alternatives considered**:
- **Sin CNI de políticas** (dejar el VPC CNI por defecto): más simple de instalar, pero viola
  directamente FR-008/FR-009/FR-010 — las políticas quedarían escritas y sin efecto. Rechazado.
- **Cilium**: más funciones (L7 policies, observabilidad eBPF), pero reemplaza el CNI de red
  completo de EKS, más riesgo de romper el enrutamiento base en una cuenta educativa con límites
  desconocidos (R5-13). Rechazado por no aportar nada que la historia necesite sobre L3/L4.

## Decisión 3: Pulsar con manifiestos estáticos versionados a mano, no un operador de terceros

**Decision**: Escribir `StatefulSet` + `Service` a mano para ZooKeeper (1 réplica), bookies (2
réplicas) y brokers (2 réplicas), en vez de instalar el *Pulsar Operator* (Helm chart oficial de
Apache Pulsar) u otro operador de Kubernetes.

**Rationale**: La constitución y el spec (Assumptions) ya fijan que Pulsar **no** es un servicio
gestionado ni contratado — el equipo configura y despliega su propio clúster, igual que en
Compose. Un operador de terceros introduce sus propios CRDs, su propio ciclo de reconciliación y
su propia superficie de fallo, que hay que aprender a depurar bajo presión de tiempo justo en el
componente marcado como el riesgo mayor (R5-11). Manifiestos estáticos son exactamente lo mismo
que ya existe en `docker-compose.yml` (un `StatefulSet` por rol, un volumen por réplica),
trasladado 1:1, lo que reduce lo nuevo que puede fallar a: (a) el `StorageClass`/PVC, y (b) el
`NetworkPolicy`. Consistente con Decisión 1 (evitar capas de indirección no imprescindibles).

**Alternatives considered**:
- **Pulsar Helm chart oficial**: automatiza mucho, pero trae su propio esquema de `values.yaml`
  con decenas de parámetros no documentados para este proyecto, y depender de Helm contradice la
  Decisión 1. Rechazado.
- **StatefulSet único todo-en-uno** (ZooKeeper+bookie+broker en el mismo pod, como el modo
  standalone de Pulsar): más simple, pero no separa los componentes que la historia pide medir
  por separado (2 brokers, 2 bookies) y no representa fielmente la topología ya validada en
  Compose. Rechazado.

**Plan alterno (activa solo si R5-11 no converge en ~4 horas de trabajo dedicado)**: reducir a 1
broker + 1 bookie (aceptando que el escenario de "no perder mensajes al eliminar un bookie" no
se pueda demostrar con redundancia, y documentarlo explícitamente como CA-3.29/limitación de la
cuenta o del tiempo disponible, nunca como "listo").

## Decisión 4: Variantes de los guiones de escenarios por archivo nuevo, no por flag de entorno

**Decision**: Cada guion existente en `escenarios/*.sh` que use comandos de Docker Compose gana
un archivo hermano `escenarios/<mismo-nombre>-k8s.sh` con la misma estructura y los mismos
criterios PASA/FALLA, pero usando comandos de `kubectl` (`kubectl scale`, `kubectl delete pod`,
`kubectl exec`) en vez de `docker compose stop`/`docker exec`. El guion original no se toca.

**Rationale**: FR-018 exige la variante "sin eliminar la existente"; un flag `--entorno=k8s`
dentro del mismo archivo mezclaría dos formas de invocar comandos y dos formas de calcular
métricas dentro de un solo script, aumentando el riesgo de romper por accidente el guion que ya
funciona contra Compose y que ya produjo evidencia en la Entrega 4 (Principio VI: no se toca lo
que ya está verificado sin necesidad). Un archivo separado es explícito sobre contra qué entorno
corre, igual que pide el documento de negocio ("cada guion sabe contra cuál de los dos entornos
está corriendo").

**Alternatives considered**:
- **Un único guion parametrizado por entorno**: menos archivos, pero mezcla dos familias de
  comandos (`docker` vs `kubectl`) con ramas condicionales en cada paso, más difícil de auditar
  línea por línea contra el criterio de aceptación correspondiente. Rechazado.

## Decisión 5: Job de Kubernetes para la preparación de Pulsar, disparado manualmente tras el *readiness* de los brokers

**Decision**: `infra/pulsar/inicializar.sh` se empaqueta en la misma imagen base (o una imagen
utilitaria con `curl`/`pulsar-admin`) y se ejecuta como un `Job` de Kubernetes
(`infra/k8s/pulsar/job-init.yaml`), con un `initContainer` o precondición que espera el
`readinessProbe` de los brokers antes de correr. El comando único de despliegue (FR-002) aplica
primero Pulsar, espera su salud, y luego el `Job`, en ese orden — igual que hoy `docker-compose.yml`
ordena `pulsar-init`/`pulsar-config` después de los brokers con `depends_on`+`condition:
service_healthy`.

**Rationale**: El guion ya es repetible (se puede correr dos veces sin romper nada, según el
documento de negocio) — no hay razón para reescribirlo; un `Job` es la forma nativa de Kubernetes
de correr una tarea de una sola vez con reintento automático si falla por una carrera transitoria
con la salud de los brokers.

**Alternatives considered**:
- **`initContainer` dentro de un pod de aplicación**: ataría la preparación del tenant al ciclo
  de vida de un servicio de dominio, sin relación lógica entre ambos. Rechazado.
- **Ejecutarlo a mano por fuera del comando único**: viola CA-3.6 (un solo comando).

## Resumen de NEEDS CLARIFICATION resueltos

Ninguno. El spec (`spec.md`) no dejó marcadores `[NEEDS CLARIFICATION]` pendientes; las cinco
decisiones de este documento resuelven las incógnitas técnicas de *cómo* implementar lo que el
spec ya definió como *qué* se necesita.
