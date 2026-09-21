#!/usr/bin/env bash
# T004 · Construye los seis Dockerfile ya existentes (sin modificarlos) y los
# publica en los repositorios ECR creados por infra/aws/terraform-eks/ecr.tf,
# etiquetados con el hash corto del commit actual — nunca "latest" (FR-004,
# mitiga R5-15: sin esto, es fácil desplegar código viejo sin darse cuenta).
#
#   bash infra/k8s/publicar-imagenes.sh

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$DIR"

REGION="${AWS_REGION:-us-east-1}"
TAG="$(git rev-parse --short HEAD)"
CUENTA="$(aws sts get-caller-identity --query Account --output text)"
REGISTRO="${CUENTA}.dkr.ecr.${REGION}.amazonaws.com"

echo "=== Publicando imágenes · tag=${TAG} · registro=${REGISTRO} ==="
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRO"

declare -A SERVICIOS=(
  [gestion-trabajos]=servicios/gestion_trabajos
  [operaciones]=servicios/operaciones
  [acreditacion]=servicios/acreditacion
  [emparejamiento]=servicios/emparejamiento
  [saga-log]=servicios/saga_log
  [bff]=servicios/bff
)

for nombre in "${!SERVICIOS[@]}"; do
  ruta="${SERVICIOS[$nombre]}"
  imagen="${REGISTRO}/hogar-alpes/${nombre}:${TAG}"
  echo
  echo "--- ${nombre} (${ruta}) -> ${imagen}"
  docker build -t "$imagen" "$ruta"
  docker push "$imagen"
done

echo
echo "=== Listo. Tag publicado: ${TAG} ==="
echo "Usar este tag en infra/k8s/desplegar.sh (variable TAG) o exportar:"
echo "  export HOGAR_ALPES_TAG=${TAG}"
