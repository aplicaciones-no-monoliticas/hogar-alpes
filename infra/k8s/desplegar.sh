#!/usr/bin/env bash
# Comando único de despliegue (CA-3.6). Orden fijado por
# specs/003-despliegue-kubernetes-aws/contracts/comandos-despliegue.md:
#   red/ -> configuracion/ -> secretos -> bases-de-datos/ -> pulsar/
#   (espera readiness de brokers) -> Job de init -> servicios/ -> bff/
#
# Idempotente: se puede correr dos veces sin romper nada (kubectl apply lo es
# por diseño; generar-secretos.sh no reemplaza secretos existentes).
#
#   bash infra/k8s/desplegar.sh [reducido|completo]

set -euo pipefail

ENTORNO="${1:-completo}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/../.." && pwd)"
REGION="${AWS_REGION:-us-east-1}"
TAG="${HOGAR_ALPES_TAG:-$(git -C "$RAIZ" rev-parse --short HEAD)}"
CUENTA="$(aws sts get-caller-identity --query Account --output text)"
REGISTRO="${CUENTA}.dkr.ecr.${REGION}.amazonaws.com"

echo "=== Desplegando Hogar de los Alpes en Kubernetes · entorno=${ENTORNO} · tag=${TAG} ==="

echo; echo "--- StorageClass"
kubectl apply -f "$DIR/entornos/storageclass.yaml"

echo; echo "--- Reglas de red (default-deny primero)"
kubectl apply -f "$DIR/red/deny-default-db.yaml"
kubectl apply -f "$DIR/red/deny-default-api.yaml"
kubectl apply -f "$DIR/red/allow-db-owners.yaml"
kubectl apply -f "$DIR/red/allow-bff.yaml"

echo; echo "--- Configuración (ConfigMap generados desde la fuente única)"
kubectl create configmap reglas-regionales \
  --from-file=reglas_regionales.json="$DIR/configuracion/reglas_regionales.json" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap variables-comunes \
  --from-env-file="$DIR/configuracion/variables-comunes.env" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap pulsar-scripts \
  --from-file="$RAIZ/infra/pulsar/inicializar.sh" \
  --from-file="$RAIZ/infra/pulsar/comun.sh" \
  --from-file="$RAIZ/infra/pulsar/topologia.env" \
  --dry-run=client -o yaml | kubectl apply -f -

echo; echo "--- Secretos de PostgreSQL"
bash "$DIR/generar-secretos.sh"

echo; echo "--- Bases de datos"
kubectl apply -f "$DIR/bases-de-datos/"
for db in trabajos operaciones acreditacion emparejamiento saga; do
  kubectl rollout status "statefulset/postgres-${db}" --timeout=180s
done

echo; echo "--- Pulsar: ZooKeeper"
kubectl apply -f "$DIR/pulsar/zookeeper.yaml"
kubectl rollout status statefulset/zookeeper --timeout=180s

echo; echo "--- Pulsar: metadatos del clúster (Job, una sola vez)"
kubectl apply -f "$DIR/pulsar/job-cluster-init.yaml"
kubectl wait --for=condition=complete job/pulsar-cluster-init --timeout=180s || true

echo; echo "--- Pulsar: bookies"
kubectl apply -f "$DIR/pulsar/bookies.yaml"
kubectl rollout status statefulset/bookie --timeout=300s

echo; echo "--- Pulsar: brokers"
kubectl apply -f "$DIR/pulsar/brokers.yaml"
kubectl rollout status deployment/broker --timeout=300s

echo; echo "--- Pulsar: tenant/namespaces/tópicos/suscripciones (Job, reutiliza inicializar.sh)"
kubectl delete job pulsar-topology-init --ignore-not-found
kubectl apply -f "$DIR/pulsar/job-topology-init.yaml"
kubectl wait --for=condition=complete job/pulsar-topology-init --timeout=300s

echo; echo "--- Servicios de dominio (imágenes: ${REGISTRO}, tag ${TAG})"
for archivo in "$DIR"/servicios/gestion-trabajos.yaml "$DIR"/servicios/operaciones.yaml \
               "$DIR"/servicios/acreditacion.yaml "$DIR"/servicios/emparejamiento.yaml \
               "$DIR"/servicios/saga-log.yaml; do
  sed -e "s#PLACEHOLDER_ECR#${REGISTRO}#g" -e "s#PLACEHOLDER_TAG#${TAG}#g" "$archivo" | kubectl apply -f -
done

echo; echo "--- BFF"
sed -e "s#PLACEHOLDER_ECR#${REGISTRO}#g" -e "s#PLACEHOLDER_TAG#${TAG}#g" "$DIR/servicios/bff.yaml" | kubectl apply -f -

if [ "$ENTORNO" = "reducido" ]; then
  echo; echo "--- Entorno reducido: bajando copias no esenciales"
  kubectl scale deployment/gestion-trabajos-api --replicas=1
  kubectl scale deployment/emparejamiento-api --replicas=1
  kubectl scale deployment/bff --replicas=1
fi

echo; echo "=== Despliegue aplicado. Verificar con: kubectl get pods -A -w ==="
echo "URL del BFF (puede tardar unos minutos en asignarse):"
echo "  kubectl get svc bff -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'"
