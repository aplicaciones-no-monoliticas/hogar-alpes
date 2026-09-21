#!/usr/bin/env bash
# Habilita el CNI que hace cumplir los NetworkPolicy (research.md Decisión 2).
# El VPC CNI de EKS (add-on por defecto) asigna IPs pero NO aplica
# NetworkPolicy — sin este paso, infra/k8s/red/*.yaml se aplicaría sin
# ningún efecto (R5-12, "el peor de los dos mundos"). Modo policy-only: se
# instala el operador de Tigera/Calico con un recurso Installation SIN
# `calicoNetwork` — así Calico no reemplaza el CNI de red de EKS (que sigue
# siendo el VPC CNI), solo agrega el enforcement de políticas (Felix).
#
#   bash infra/k8s/instalar-calico.sh

set -euo pipefail

VERSION_CALICO="v3.28.0"

echo "=== Instalando el operador de Tigera/Calico ${VERSION_CALICO} (modo policy-only) ==="
kubectl create -f "https://raw.githubusercontent.com/projectcalico/calico/${VERSION_CALICO}/manifests/tigera-operator.yaml"

echo "Esperando a que el operador quede listo..."
kubectl -n tigera-operator rollout status deployment/tigera-operator --timeout=180s

echo "Aplicando el recurso Installation sin calicoNetwork (deja el enrutamiento al VPC CNI)..."
cat <<'EOF' | kubectl apply -f -
apiVersion: operator.tigera.io/v1
kind: Installation
metadata:
  name: default
spec: {}
---
apiVersion: operator.tigera.io/v1
kind: APIServer
metadata:
  name: default
spec: {}
EOF

echo "Esperando a que Calico quede listo..."
kubectl -n calico-system rollout status deployment/calico-kube-controllers --timeout=300s
kubectl -n calico-system get pods

echo "=== Calico instalado — NetworkPolicy ahora se hace cumplir ==="
