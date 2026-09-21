# Contrato: comandos de operación del despliegue en Kubernetes

Esta historia no expone una API nueva a otros sistemas — el contrato observable es el conjunto de
comandos que el `README` promete (CA-3.6, CA-3.7, CA-3.26) y su resultado esperado. Cualquier
implementación de `/speckit-tasks` debe hacer que estos comandos existan y se comporten como se
describe aquí.

## Crear el clúster (una sola vez, no parte del "comando único" de despliegue)

```bash
cd infra/aws/terraform-eks
terraform init
terraform apply -var="ssh_cidr=<TU-IP>/32"
```

**Postcondición**: un clúster EKS sano, con `kubectl get nodes` mostrando todos los nodos en
`Ready`, y el `StorageClass` `gp3` disponible (`kubectl get storageclass`).

## Publicar imágenes (parte del flujo, antes de cada despliegue de código nuevo)

```bash
infra/k8s/publicar-imagenes.sh   # construye los 6 Dockerfile existentes, etiqueta con
                                   # git rev-parse --short HEAD, hace push a ECR
```

**Postcondición**: seis repositorios ECR con una imagen nueva etiquetada con el hash del commit
actual; `docker images` / `aws ecr describe-images` confirma la etiqueta.

## Desplegar (comando único, CA-3.6)

```bash
infra/k8s/desplegar.sh [reducido|completo]   # default: completo
```

**Contrato**:
- Aplica, en orden: `red/` (NetworkPolicy default-deny primero) → `configuracion/` (ConfigMap) →
  secretos generados → `bases-de-datos/` → `pulsar/` (zookeeper, bookies, brokers) → espera
  *readiness* de los brokers → `pulsar/job-init.yaml` → espera a que el `Job` termine → `servicios/`
  (los seis, API antes que consumidor) → `servicios/bff/`.
- **Postcondición observable**: `kubectl get pods -A` sin pods en `CrashLoopBackOff` ni
  `Pending` después de un tiempo de espera razonable; `kubectl get svc bff` con una
  `EXTERNAL-IP` asignada.
- Es **idempotente**: correrlo dos veces sobre el mismo clúster no debe fallar ni duplicar
  recursos (mismo principio que ya cumple `infra/pulsar/inicializar.sh`).

## Verificar (no es un solo comando — es la checklist que exige CA-3.2 a CA-3.5, CA-3.11 a CA-3.19)

Ver `quickstart.md` para la secuencia completa de verificación paso a paso.

## Destruir (comando único, CA-3.7)

```bash
infra/k8s/destruir.sh          # kubectl delete de todo lo aplicado por desplegar.sh
cd infra/aws/terraform-eks && terraform destroy -var="ssh_cidr=<TU-IP>/32"
```

**Postcondición**: `aws eks list-clusters` ya no muestra el clúster; ningún volumen EBS asociado
a los PVC sigue existiendo (`aws ec2 describe-volumes` filtrado por el tag del proyecto);
`terraform destroy` termina en éxito sin recursos huérfanos.

## Comprobación de salud por tipo de componente (contrato interno, R5-16)

| Tipo de componente | Mecanismo de *readiness*/*liveness* |
|---|---|
| Servicio con API HTTP | `GET /health` (ya existe en los seis servicios — Restricciones Técnicas de la constitución) como `httpGet` probe |
| Consumidor (sin API) | Comprobación distinta: el propio proceso expone su estado de conexión al broker por un archivo/socket local que un `exec` probe verifica (ver `research.md` si se detalla en Fase de implementación), o se infiere indirectamente de que el proceso sigue vivo (`liveness`) + que su suscripción avanza (`readiness` mediante consulta al *cursor* de Pulsar desde el guion de verificación, no desde el probe) — el guion de escenario de disponibilidad (`escenarios/*-k8s.sh`) es quien prueba en la práctica que "colgado" se detecta, según R5-16 |
| PostgreSQL | `pg_isready` como probe |
| ZooKeeper / bookies / brokers | Los *health check* HTTP/TCP que cada uno ya expone en su imagen oficial de Apache Pulsar |
