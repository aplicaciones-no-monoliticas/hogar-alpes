# Quickstart: validar el despliegue en Kubernetes sobre AWS

Guía para comprobar, de punta a punta, que esta historia funciona — pensada para que alguien que
**no participó** en la implementación pueda seguirla (Definición de terminado del spec).

## Prerrequisitos

- Cuenta de AWS con permisos para crear EKS, EC2 (node group), EBS, ECR, VPC.
- CLI instaladas: `aws`, `terraform` (>= 1.5), `kubectl`, `docker`.
- Verificar primero qué permite la cuenta (R5-13, orden de trabajo sugerido paso 1): tipos de
  instancia disponibles, límite de nodos, si EKS está habilitado. Si algo falta, documentarlo
  como CA-3.29 antes de continuar.

## 1. Crear el clúster

```bash
cd infra/aws/terraform-eks
terraform init
terraform apply -var="ssh_cidr=<TU-IP>/32"
kubectl get nodes            # esperar todos en Ready
kubectl get storageclass     # confirmar "gp3" disponible
```

## 2. Publicar las imágenes

```bash
infra/k8s/publicar-imagenes.sh
aws ecr describe-images --repository-name hogar-alpes/bff \
  --query 'imageDetails[*].imageTags'   # confirmar que aparece el hash del commit actual
```

## 3. Desplegar el sistema completo

```bash
infra/k8s/desplegar.sh completo
kubectl get pods -A -w       # esperar a que todos queden Running/Completed (Job de init)
```

Ver `contracts/comandos-despliegue.md` para el contrato exacto de qué hace este comando y en qué
orden.

## 4. Verificar que quedó sano (CA-3.2, CA-3.5)

```bash
kubectl get pods -l tier=app          # los seis servicios, todas sus copias, Running
kubectl get statefulset -n hogar-alpes  # 5 postgres + zookeeper + bookies, todas READY
kubectl exec -it <pod-broker> -- pulsar-admin topics list hogar-alpes/trabajos/andina
kubectl exec -it <pod-broker> -- pulsar-admin brokers list <cluster>   # 2 brokers
```

## 5. Acceder por el BFF y correr Postman (CA-3.3, CA-3.4)

```bash
BFF_URL=$(kubectl get svc bff -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl "http://${BFF_URL}/health"
```

En Postman: duplicar/editar el entorno de la colección `hogar-alpes-bff.postman_collection.json`
para apuntar a `http://${BFF_URL}`, correr la colección completa → todas las carpetas en verde.

## 6. Verificar el aislamiento de red (CA-3.11 a CA-3.14)

```bash
escenarios/red-k8s.sh
```

Ver el contrato completo de qué prueba este guion en `contracts/politicas-red.md`. Resultado
esperado: todas las comprobaciones PASA, reportadas en `docs/resultados/`.

## 7. Verificar persistencia y auto-recuperación (CA-3.16 a CA-3.19)

```bash
# Un servicio se recupera solo
kubectl delete pod -l app=gestion-trabajos-api --field-selector status.phase=Running | head -1
kubectl get pods -l app=gestion-trabajos-api -w   # nuevo pod Running en segundos

# Una base de datos conserva sus datos
kubectl delete pod postgres-trabajos-0
# esperar a que vuelva Running, luego reconsultar un dato ya conocido vía la API

# Un bookie conserva mensajes y posición de suscripción
kubectl delete pod bookie-0
# releer el offset/backlog de una suscripción conocida antes/después con pulsar-admin
```

## 8. Correr los escenarios de calidad traducidos (CA-3.20 a CA-3.25)

```bash
escenarios/disponibilidad-k8s.sh
escenarios/escalabilidad-k8s.sh
escenarios/region-nueva-k8s.sh
escenarios/pais-nuevo-k8s.sh
escenarios/adaptador-persistencia-k8s.sh
```

Cada uno escribe su resultado en `docs/resultados/`, identificado como corrido en Kubernetes
(nunca mezclado con los resultados de Compose ya existentes — SC-006).

## 9. Confirmar que Compose sigue intacto (CA-3.8 — criterio duro)

```bash
git status                    # confirmar que docker-compose.yml no cambió
docker compose down -v && docker compose up -d --build
# repetir la verificación básica de salud ya usada en la Entrega 4
```

## 10. Destruir todo (CA-3.7)

```bash
infra/k8s/destruir.sh
cd infra/aws/terraform-eks && terraform destroy -var="ssh_cidr=<TU-IP>/32"
aws eks list-clusters                          # ya no aparece
aws ec2 describe-volumes --filters "Name=tag:Proyecto,Values=hogar-alpes"  # sin volúmenes huérfanos
```

## Resultado esperado global

Al terminar los pasos 1-9, los treinta criterios de aceptación de `spec.md` quedan verificados o
explícitamente documentados como limitación (CA-3.29); el paso 10 confirma que no queda ningún
recurso de AWS cobrando después de la verificación.
