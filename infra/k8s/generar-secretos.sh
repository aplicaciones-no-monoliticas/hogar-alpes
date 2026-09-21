#!/usr/bin/env bash
# Genera una contraseña aleatoria distinta por cada una de las 5 instancias
# de PostgreSQL y las aplica como Secret de Kubernetes. Nunca escribe un
# valor en disco de forma persistente ni en un archivo versionado (FR-012,
# CA-3.15). Idempotente: si el Secret ya existe, no lo reemplaza (para no
# invalidar el volumen de datos ya escrito con la contraseña anterior).
#
#   bash infra/k8s/generar-secretos.sh

set -euo pipefail

USUARIO="hogaralpes"

crear_secreto() {
  local nombre="$1" base_datos="$2" host="$3"
  if kubectl get secret "$nombre" >/dev/null 2>&1; then
    echo "  existe  $nombre"
    return
  fi
  local password
  password="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
  local uri="postgresql+psycopg2://${USUARIO}:${password}@${host}:5432/${base_datos}"
  kubectl create secret generic "$nombre" \
    --from-literal=usuario="$USUARIO" \
    --from-literal=password="$password" \
    --from-literal=database_uri="$uri"
  echo "  creado  $nombre"
}

echo "=== Generando secretos de PostgreSQL ==="
crear_secreto postgres-trabajos-credenciales       gestion_trabajos postgres-trabajos
crear_secreto postgres-operaciones-credenciales    operaciones      postgres-operaciones
crear_secreto postgres-acreditacion-credenciales   acreditacion     postgres-acreditacion
crear_secreto postgres-emparejamiento-credenciales emparejamiento   postgres-emparejamiento
crear_secreto postgres-saga-credenciales           saga_log         postgres-saga
echo "=== Listo ==="
