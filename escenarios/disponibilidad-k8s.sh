#!/usr/bin/env bash
# US-03 · CA-3.20 — Disponibilidad: bajar a cero el consumidor de Operaciones
# no debe afectar a Gestión de Trabajos; al volver, procesa el 100% acumulado
# sin duplicar. Variante Kubernetes de escenarios/escenario-6.sh.
#
# Uso:
#   escenarios/disponibilidad-k8s.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"
FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/disponibilidad-k8s-$FECHA.md"

fallos=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then resultado "  PASA   $id · $detalle"; else resultado "  FALLA  $id · $detalle"; fallos=$((fallos + 1)); fi
}

backlog_operaciones() {
  local pod_broker
  pod_broker="$(kubectl get pod -l app=broker -o jsonpath='{.items[0].metadata.name}')"
  kubectl exec "$pod_broker" -- bin/pulsar-admin topics partitioned-stats \
    persistent://hogar-alpes/trabajos/evt-trabajo-andina 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('subscriptions',{}).get('operaciones',{}).get('msgBacklog','?'))" 2>/dev/null || echo "?"
}

resultado "# Disponibilidad en Kubernetes — $FECHA"
resultado ""
resultado "## 1. Bajar el consumidor de Operaciones a cero copias"
kubectl scale deployment/operaciones-consumidor --replicas=0 >>"$SALIDA" 2>&1
sleep 5
copias="$(kubectl get deployment operaciones-consumidor -o jsonpath='{.status.replicas}' 2>/dev/null || echo 0)"
criterio CA-3.20a "$([ "${copias:-0}" = "0" ] && echo 0 || echo 1)" "copias de operaciones-consumidor = ${copias:-0} (esperado 0)"

resultado ""
resultado "## 2. Gestión de Trabajos sigue respondiendo mientras Operaciones está caído"
pod_gt="$(kubectl get pod -l app=gestion-trabajos-api -o jsonpath='{.items[0].metadata.name}')"
codigo="$(kubectl exec "$pod_gt" -- python3 -c "
import urllib.request
try:
    print(urllib.request.urlopen('http://localhost:5000/health', timeout=3).status)
except Exception:
    print('error')
" 2>/dev/null)"
criterio CA-3.20b "$([ "$codigo" = "200" ] && echo 0 || echo 1)" "gestion-trabajos-api /health → $codigo"

resultado ""
resultado "## 3. Volver a levantar el consumidor: procesa el 100% sin duplicar"
kubectl scale deployment/operaciones-consumidor --replicas=1 >>"$SALIDA" 2>&1
kubectl rollout status deployment/operaciones-consumidor --timeout=120s >>"$SALIDA" 2>&1
sleep 15
backlog="$(backlog_operaciones)"
criterio CA-3.20c "$([ "$backlog" = "0" ] && echo 0 || echo 1)" "backlog de la suscripción 'operaciones' tras reanudar = $backlog (esperado 0, sin duplicar)"

resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"; exit 1; fi
resultado "PASA · disponibilidad verificada en Kubernetes · detalle en $SALIDA"
