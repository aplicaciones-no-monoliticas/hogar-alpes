#!/usr/bin/env bash
# Variante Kubernetes de la verificación de aislamiento de red (US-03, CA-3.11
# a CA-3.14). Implementa exactamente lo que describe
# specs/003-despliegue-kubernetes-aws/contracts/politicas-red.md: prueba que
# una conexión PROHIBIDA efectivamente falla — nunca infiere el aislamiento
# de que la NetworkPolicy exista (R5-12, Principio VI de la constitución).
#
# Uso:
#   escenarios/red-k8s.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/red-k8s-$FECHA.md"

fallos=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then
    resultado "  PASA   $id · $detalle"
  else
    resultado "  FALLA  $id · $detalle"
    fallos=$((fallos + 1))
  fi
}

# Ejecuta un intento de conexión TCP DESDE un pod con label "servicio=$1"
# HACIA "$2:$3", con timeout de 3s. Devuelve 0 si conecta, 1 si falla.
intentar_tcp() {
  local origen_label="$1" destino_host="$2" destino_puerto="$3"
  local pod
  pod="$(kubectl get pod -l "servicio=${origen_label}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)"
  [ -z "$pod" ] && pod="$(kubectl get pod -l "app=${origen_label}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)"
  if [ -z "$pod" ]; then
    echo "sin-pod"
    return
  fi
  if kubectl exec "$pod" -- timeout 3 bash -c "echo > /dev/tcp/${destino_host}/${destino_puerto}" >/dev/null 2>&1; then
    echo "conecta"
  else
    echo "falla"
  fi
}

resultado "# Aislamiento de red en Kubernetes — $FECHA"
resultado ""
resultado "## 1. Las nueve conexiones prohibidas servicio→base ajena"

declare -A BASES=(
  [postgres-trabajos]=gestion-trabajos
  [postgres-operaciones]=operaciones
  [postgres-acreditacion]=acreditacion
  [postgres-emparejamiento]=emparejamiento
  [postgres-saga]=saga-log
)
SERVICIOS=(gestion-trabajos operaciones acreditacion emparejamiento saga-log)

n=1
for base in "${!BASES[@]}"; do
  dueno="${BASES[$base]}"
  for servicio in "${SERVICIOS[@]}"; do
    [ "$servicio" = "$dueno" ] && continue
    r="$(intentar_tcp "$servicio" "$base" 5432)"
    criterio "RED-$n" "$([ "$r" = "falla" ] && echo 0 || echo 1)" \
      "$servicio → $base:5432 → $r (esperado: falla)"
    n=$((n + 1))
  done
done

resultado ""
resultado "## 2. Ningún servicio de dominio alcanza a otro por HTTP (solo el BFF)"

APIS=(gestion-trabajos-api operaciones-api acreditacion-api emparejamiento-api saga-log-api)
for origen in "${SERVICIOS[@]}"; do
  for destino in "${APIS[@]}"; do
    # No probar contra su propia API
    [[ "$destino" == "$origen"* ]] && continue
    r="$(intentar_tcp "$origen" "$destino" 5000)"
    criterio "RED-HTTP-${origen}-${destino}" "$([ "$r" = "falla" ] && echo 0 || echo 1)" \
      "$origen → $destino:5000 → $r (esperado: falla)"
  done
done

resultado ""
resultado "## 3. Control positivo: el BFF SÍ alcanza a los cinco"
for destino in "${APIS[@]}"; do
  pod_bff="$(kubectl get pod -l app=bff -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)"
  if [ -z "$pod_bff" ]; then
    criterio "RED-BFF-${destino}" 1 "no hay pod de bff corriendo"
    continue
  fi
  codigo="$(kubectl exec "$pod_bff" -- python3 -c "
import urllib.request
try:
    print(urllib.request.urlopen('http://${destino}:5000/health', timeout=3).status)
except Exception:
    print('error')
" 2>/dev/null)"
  criterio "RED-BFF-${destino}" "$([ "$codigo" = "200" ] && echo 0 || echo 1)" \
    "bff → ${destino}/health → $codigo (esperado: 200 — confirma que el aislamiento no bloquea de más)"
done

resultado ""
resultado "## 4. Nada salvo el BFF está expuesto hacia internet"
BFF_URL="$(kubectl get svc bff -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null)"
if [ -n "$BFF_URL" ]; then
  codigo_bff="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://${BFF_URL}/health" || echo 000)"
  criterio "RED-EXT-BFF" "$([ "$codigo_bff" = "200" ] && echo 0 || echo 1)" \
    "BFF externo → $codigo_bff (esperado 200)"
else
  criterio "RED-EXT-BFF" 1 "el Service bff no tiene EXTERNAL-IP asignada todavía"
fi
for svc in postgres-trabajos broker; do
  ext="$(kubectl get svc "$svc" -o jsonpath='{.spec.type}' 2>/dev/null)"
  criterio "RED-EXT-${svc}" "$([ "$ext" != "LoadBalancer" ] && echo 0 || echo 1)" \
    "Service $svc tipo=$ext (esperado: ClusterIP/headless, nunca LoadBalancer)"
done

resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · aislamiento de red verificado en Kubernetes · detalle en $SALIDA"
