#!/usr/bin/env bash
# Comando único de destrucción (CA-3.7). Borra todo lo que aplicó
# desplegar.sh, incluidos los volúmenes EBS que StorageClass gp3 deja en
# "Retain" (si no se borran a mano, quedan cobrando aparte del clúster).
#
#   bash infra/k8s/destruir.sh

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Destruyendo el despliegue de Hogar de los Alpes ==="

kubectl delete -f "$DIR/servicios/bff.yaml" --ignore-not-found 2>/dev/null || true
for archivo in "$DIR"/servicios/*.yaml; do
  kubectl delete -f "$archivo" --ignore-not-found 2>/dev/null || true
done

kubectl delete job pulsar-topology-init pulsar-cluster-init --ignore-not-found
kubectl delete -f "$DIR/pulsar/brokers.yaml" --ignore-not-found
kubectl delete -f "$DIR/pulsar/bookies.yaml" --ignore-not-found
kubectl delete -f "$DIR/pulsar/zookeeper.yaml" --ignore-not-found
kubectl delete -f "$DIR/bases-de-datos/" --ignore-not-found

kubectl delete -f "$DIR/red/allow-bff.yaml" --ignore-not-found
kubectl delete -f "$DIR/red/allow-db-owners.yaml" --ignore-not-found
kubectl delete -f "$DIR/red/deny-default-api.yaml" --ignore-not-found
kubectl delete -f "$DIR/red/deny-default-db.yaml" --ignore-not-found

kubectl delete configmap reglas-regionales variables-comunes pulsar-scripts --ignore-not-found
for s in postgres-trabajos postgres-operaciones postgres-acreditacion postgres-emparejamiento postgres-saga; do
  kubectl delete secret "${s}-credenciales" --ignore-not-found
done

echo; echo "--- PersistentVolumeClaim (StatefulSet no las borra solo — hay que hacerlo explícito) ---"
# Un PVC eliminado con StorageClass "Retain" NO borra el volumen EBS (por
# diseño); solo libera el finalizer kubernetes.io/pv-protection para que el
# PV pueda terminar de eliminarse. Borrar el volumen EBS por AWS CLI ANTES
# de esto deja el PV colgado en Terminating (bug encontrado y corregido en
# esta misma sesión — docs/decisiones.md §US-03).
kubectl delete pvc --all --ignore-not-found

echo; echo "--- Volúmenes EBS que quedaron en Retain (StorageClass gp3) ---"
kubectl get pv -o jsonpath='{range .items[?(@.spec.storageClassName=="gp3")]}{.spec.csi.volumeHandle}{"\n"}{end}' 2>/dev/null | while read -r vol; do
  [ -z "$vol" ] && continue
  echo "borrando volumen EBS $vol"
  aws ec2 delete-volume --volume-id "$vol" 2>/dev/null || echo "  (ya no existe o falló, revisar a mano)"
done
kubectl delete pv --all --ignore-not-found

kubectl delete -f "$DIR/entornos/storageclass.yaml" --ignore-not-found

echo "=== Recursos dentro del clúster destruidos. Ahora: cd infra/aws/terraform-eks && terraform destroy ==="
