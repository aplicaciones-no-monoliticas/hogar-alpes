#!/usr/bin/env bash
# Configura Pulsar Manager la primera vez que se levanta — crea el usuario
# admin (Pulsar Manager no trae ninguno por defecto) y registra el entorno
# que apunta al clúster real. Después de correr esto una sola vez, entra a
# http://localhost:9527 (o al puerto publicado en AWS) con las credenciales
# que se imprimen abajo.
#
# Uso:
#   docker compose --profile demo up -d pulsar-manager
#   infra/pulsar/pulsar-manager-setup.sh
#   infra/pulsar/pulsar-manager-setup.sh --url http://<IP-EC2>:7750   # contra AWS

set -euo pipefail

BASE_URL="http://localhost:7750"
USUARIO="admin"
CLAVE="${PULSAR_MANAGER_CLAVE:-$(openssl rand -hex 12)}"

while [ $# -gt 0 ]; do
  case "$1" in
    --url) BASE_URL="$2"; shift 2 ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

echo "Esperando a que Pulsar Manager responda en $BASE_URL…"
for _ in $(seq 1 30); do
  if curl -sf "$BASE_URL/pulsar-manager/csrf-token" >/dev/null 2>&1; then break; fi
  sleep 2
done

CSRF_TOKEN="$(curl -s "$BASE_URL/pulsar-manager/csrf-token")"
if [ -z "$CSRF_TOKEN" ]; then
  echo "FALLA · no se pudo obtener el token CSRF — ¿está pulsar-manager arriba? (docker compose --profile demo up -d pulsar-manager)" >&2
  exit 1
fi

respuesta="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "X-XSRF-TOKEN: $CSRF_TOKEN" -H "Cookie: XSRF-TOKEN=$CSRF_TOKEN;" \
  -H 'Content-Type: application/json' \
  -X PUT "$BASE_URL/pulsar-manager/users/superuser" \
  -d "{\"name\":\"$USUARIO\",\"password\":\"$CLAVE\",\"description\":\"admin\",\"email\":\"admin@hogar-alpes.local\"}")"

if [ "$respuesta" != "200" ] && [ "$respuesta" != "409" ]; then
  echo "FALLA · el backend respondió $respuesta creando el usuario" >&2
  exit 1
fi
[ "$respuesta" = "409" ] && echo "(el usuario ya existía — se reutiliza)"

cat <<EOF

Listo. Entra a la UI y añade el entorno a mano (una sola vez, no tiene API pública):

  1. http://localhost:9527  (o http://<IP>:9527 en AWS)
  2. Usuario: $USUARIO
     Clave:   $CLAVE
  3. "New Environment" → Environment name: cluster-hda
     Service URL: http://broker-1:8080

Guarda la clave — no vuelve a imprimirse (${PULSAR_MANAGER_CLAVE:+se usó la que pasaste en PULSAR_MANAGER_CLAVE}${PULSAR_MANAGER_CLAVE:-se generó al azar}).
EOF
