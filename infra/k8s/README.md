# Despliegue en Kubernetes sobre AWS (US-03)

Tercera forma de desplegar Hogar de los Alpes, además de Docker Compose local y la EC2 de
`infra/aws/terraform/`. **No reemplaza a ninguna de las dos** — coexiste con ellas
(CA-3.8, `docs/us-entrega-5/US-03-despliegue-kubernetes-aws.md`).

Todo el sistema (seis servicios, cinco PostgreSQL, el clúster de Pulsar) corre dentro de un
clúster EKS. Solo el BFF queda expuesto hacia afuera.

## Requisitos previos

- Cuenta de AWS con permisos para EKS, EC2, EBS, ECR, VPC, IAM.
- CLI instaladas: `aws` (con credenciales configuradas — `aws sts get-caller-identity` debe
  responder), `terraform >= 1.5`, `kubectl`, `docker`, `openssl`.
- Verificar primero qué permite la cuenta (orden de trabajo, paso 1 del documento de negocio):
  tipos de instancia disponibles para EKS, cuota de vCPU, si el servicio EKS está habilitado.
  Cualquier limitación encontrada se documenta abajo en **Limitaciones encontradas**, nunca
  como "no se pudo" sin más (CA-3.29).

## 1. Crear el clúster

```bash
cd infra/aws/terraform-eks
terraform init
terraform apply
aws eks update-kubeconfig --name hogar-alpes-eks --region us-east-1
kubectl get nodes                 # esperar Ready
```

Este paso también crea los seis repositorios ECR (`infra/aws/terraform-eks/ecr.tf`).

## 2. Habilitar el aislamiento de red (Calico)

```bash
bash infra/k8s/instalar-calico.sh
```

Sin este paso, las `NetworkPolicy` del paso 4 se aplicarían sin ningún efecto (R5-12): el VPC
CNI de EKS por defecto **no** hace cumplir `NetworkPolicy`.

## 3. Publicar las imágenes

```bash
bash infra/k8s/publicar-imagenes.sh
```

Construye los seis `Dockerfile` ya existentes (sin modificarlos) y los publica en ECR,
etiquetados con `git rev-parse --short HEAD` — nunca `latest` (FR-004).

## 4. Desplegar (un solo comando, CA-3.6)

```bash
bash infra/k8s/desplegar.sh completo   # o "reducido" para menos copias
```

Aplica, en orden, las reglas de red, la configuración, los secretos, las cinco bases de datos,
Pulsar (ZooKeeper → metadatos → bookies → brokers → tópicos/suscripciones) y los seis servicios
+ BFF. Es idempotente.

## 5. Verificar

```bash
kubectl get pods -A -w                              # todo Running/Completed
BFF_URL=$(kubectl get svc bff -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl "http://${BFF_URL}/health"
bash escenarios/red-k8s.sh                           # aislamiento de red (CA-3.11-3.14)
bash escenarios/recuperacion-k8s.sh                  # persistencia y auto-recuperación (CA-3.16-3.19)
```

En Postman: entorno `postman/bff-k8s.postman_environment.json`, reemplazar
`<EXTERNAL-IP-DEL-SERVICE-BFF>` por `$BFF_URL` y correr la colección completa (CA-3.4).

Ver `specs/003-despliegue-kubernetes-aws/quickstart.md` para la secuencia completa paso a paso,
incluidos los cinco escenarios de calidad traducidos.

### Trazabilidad por identificador de correlación (CA-3.10b, FR-020)

Con los procesos repartidos en varios pods, buscar un `correlation_id` conocido en los registros
de todos a la vez:

```bash
kubectl logs -l tier=app --all-containers --prefix --since=1h | grep '<correlation-id>'
```

`--prefix` antepone el pod de origen a cada línea, así la cadena completa de la petición queda
ordenable por servicio aunque los procesos estén en nodos distintos.

## 6. Destruir (un solo comando, CA-3.7)

```bash
bash infra/k8s/destruir.sh
cd infra/aws/terraform-eks && terraform destroy
```

`destruir.sh` también borra los volúmenes EBS que el `StorageClass` `gp3` deja en `Retain` —
sin ese paso quedarían cobrando aparte del clúster.

## Costo aproximado

| Componente | Costo aproximado |
|---|---|
| Control plane EKS | ~USD 0.10/hora (fijo, cobra mientras el clúster exista) |
| Node group (3 × t3.large on-demand, us-east-1) | ~USD 0.25/hora ≈ USD 6/día |
| Volúmenes EBS gp3 (5×10Gi Postgres + 5Gi ZooKeeper + 2×20Gi bookies ≈ 95Gi) | ~USD 0.08/GB-mes ≈ USD 0.25/día |
| `LoadBalancer` del BFF (Network Load Balancer) | ~USD 0.0225/hora ≈ USD 0.55/día |
| **Total aproximado** | **~USD 0.45–0.50/hora · ~USD 11/día** mientras el clúster exista |

**Cómo dejar de pagar**: el paso 6 (`destruir.sh` + `terraform destroy`) es la única forma de
dejar de pagar por completo — a diferencia de la EC2 de Compose, un clúster EKS **no se puede
"apagar"** sin destruirlo; el control plane cobra mientras exista, esté o no usándose. Por eso el
clúster se levanta solo para probar y para la sustentación, nunca se deja corriendo entre
sesiones de trabajo (R5-14).

## Limitaciones encontradas

Ninguna. La cuenta usada para verificar esta historia permitió EKS, el node group de 3×
t3.large, el add-on `aws-ebs-csi-driver`, los 6 repositorios ECR y el `LoadBalancer` del BFF sin
ajustes de cuota (32 vCPU on-demand disponibles, verificado antes de empezar). Tres problemas
de configuración sí aparecieron al desplegar contra el clúster real — ninguno es una limitación
de la cuenta, los tres son ajustes a los manifiestos, documentados con su corrección en
`docs/decisiones.md` §US-03:

1. PostgreSQL sobre un volumen EBS nuevo necesita `PGDATA` en un subdirectorio (no la raíz del
   volumen, que trae `lost+found`).
2. ZooKeeper/bookies necesitan `securityContext.fsGroup` para poder escribir en un volumen EBS
   nuevo (la imagen corre como uid no-root).
3. El driver CSI de EBS necesita IRSA (rol de IAM ligado a su `ServiceAccount`), no alcanza con
   los permisos del rol de los nodos — sin esto, `aws-ebs-csi-driver` queda en
   `CrashLoopBackOff` por no poder llegar al IMDS del nodo desde un pod.

## Estructura

```text
infra/aws/terraform-eks/   Clúster EKS + node group + ECR (independiente de infra/aws/terraform/)
infra/k8s/
├── pulsar/                 ZooKeeper, bookies, brokers, Jobs de inicialización
├── bases-de-datos/         Las cinco instancias de PostgreSQL
├── servicios/               Los seis servicios (API + consumidor)
├── configuracion/           ConfigMap de reglas regionales + variables comunes
├── red/                     NetworkPolicy (aislamiento por base + "solo BFF → *")
├── entornos/                 StorageClass (kustomize overlays pendientes de ampliar)
├── desplegar.sh / destruir.sh / publicar-imagenes.sh / generar-secretos.sh / instalar-calico.sh
```

## Ver también

- `specs/003-despliegue-kubernetes-aws/` — spec, plan, research, data-model, contratos, tasks.
- `contracts/politicas-red.md` y `contracts/comandos-despliegue.md` — el contrato exacto de
  verificación de red y de los comandos de operación.
