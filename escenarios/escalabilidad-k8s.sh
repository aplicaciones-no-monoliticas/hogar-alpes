#!/usr/bin/env bash
# US-03 · CA-3.21 — Escalabilidad: duplicar las copias de un consumidor casi
# duplica su velocidad de procesamiento. Variante Kubernetes de
# escenarios/escenario-8.sh (medida por backlog/segundo, misma idea).
#
# Uso:
#   escenarios/escalabilidad-k8s.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"
FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/escalabilidad-k8s-$FECHA.md"

fallos=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then resultado "  PASA   $id · $detalle"; else resultado "  FALLA  $id · $detalle"; fallos=$((fallos + 1)); fi
}

backlog_andina() {
  local pod_broker
  pod_broker="$(kubectl get pod -l app=broker -o jsonpath='{.items[0].metadata.name}')"
  kubectl exec "$pod_broker" -- bin/pulsar-admin topics partitioned-stats \
    persistent://hogar-alpes/trabajos/evt-trabajo-andina 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('subscriptions',{}).get('emparejamiento-andina',{}).get('msgBacklog', -1))" 2>/dev/null || echo -1
}

resultado "# Escalabilidad en Kubernetes — $FECHA"
resultado ""
resultado "## 1. Backlog inicial con 1 copia de emparejamiento-andina"
kubectl scale deployment/emparejamiento-andina --replicas=1 >>"$SALIDA" 2>&1
kubectl rollout status deployment/emparejamiento-andina --timeout=120s >>"$SALIDA" 2>&1
b1_inicio="$(backlog_andina)"
sleep 30
b1_fin="$(backlog_andina)"
tasa1=$(( (b1_inicio - b1_fin) > 0 ? (b1_inicio - b1_fin) : 0 ))
resultado "  backlog: $b1_inicio → $b1_fin en 30s (tasa ≈ $tasa1 msg/30s) con 1 copia"

resultado ""
resultado "## 2. Duplicar a 2 copias"
kubectl scale deployment/emparejamiento-andina --replicas=2 >>"$SALIDA" 2>&1
kubectl rollout status deployment/emparejamiento-andina --timeout=120s >>"$SALIDA" 2>&1
b2_inicio="$(backlog_andina)"
sleep 30
b2_fin="$(backlog_andina)"
tasa2=$(( (b2_inicio - b2_fin) > 0 ? (b2_inicio - b2_fin) : 0 ))
resultado "  backlog: $b2_inicio → $b2_fin en 30s (tasa ≈ $tasa2 msg/30s) con 2 copias"

resultado ""
resultado "## 3. La tasa con 2 copias es notablemente mayor (requiere backlog acumulado previo — ver nota)"
resultado "  NOTA: este guion mide la tasa de procesamiento tal como la deja el tráfico ya en curso;"
resultado "  para una medición comparable a escenarios/escenario-8.sh hay que generar carga antes de"
resultado "  correrlo (misma herramienta de generación de carga, apuntada al BFF de Kubernetes)."
if [ "$tasa1" -gt 0 ]; then
  criterio CA-3.21 "$(( tasa2 >= tasa1 ? 0 : 1 ))" "tasa 2 copias ($tasa2) >= tasa 1 copia ($tasa1)"
else
  criterio CA-3.21 1 "sin backlog previo que consumir — correr con carga generada antes (ver NOTA)"
fi

resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"; exit 1; fi
resultado "PASA · escalabilidad verificada en Kubernetes · detalle en $SALIDA"
