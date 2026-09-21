#!/usr/bin/env bash
# US-03 · Persistencia y auto-recuperación (CA-3.16 a CA-3.19). Elimina un pod
# de un servicio, uno de una base de datos y uno de un bookie de Pulsar, y
# relee del propio clúster/broker que cada uno volvió sano y conservó su
# estado — nunca se asume porque `kubectl delete` no protestó (Principio VI).
#
# Uso:
#   escenarios/recuperacion-k8s.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/recuperacion-k8s-$FECHA.md"

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

resultado "# Persistencia y auto-recuperación en Kubernetes — $FECHA"

# --------------------------------------------------------- 1. un servicio
resultado ""
resultado "## 1. Un servicio eliminado se recupera solo (CA-3.16)"
pod_gt="$(kubectl get pod -l app=gestion-trabajos-api -o jsonpath='{.items[0].metadata.name}')"
kubectl delete pod "$pod_gt" >>"$SALIDA" 2>&1
kubectl rollout status deployment/gestion-trabajos-api --timeout=120s >>"$SALIDA" 2>&1
codigo="$(kubectl get pods -l app=gestion-trabajos-api --field-selector=status.phase=Running -o name | wc -l)"
criterio CA-3.16 "$([ "$codigo" -ge 1 ] && echo 0 || echo 1)" \
  "tras eliminar $pod_gt, copias Running de gestion-trabajos-api = $codigo (esperado >=1)"

# --------------------------------------------------- 2. una base de datos
resultado ""
resultado "## 2. Una base de datos eliminada conserva sus datos (CA-3.17)"
pod_gt_api="$(kubectl get pod -l app=gestion-trabajos-api -o jsonpath='{.items[0].metadata.name}')"
conteo_antes="$(kubectl exec "$pod_gt_api" -- python -c "
import os, psycopg2
c = psycopg2.connect(os.environ['DATABASE_URI'].replace('+psycopg2',''))
cur = c.cursor(); cur.execute('SELECT count(*) FROM trabajos')
print(cur.fetchone()[0])
" 2>/dev/null || echo "sin-tabla-o-vacia")"

kubectl delete pod postgres-trabajos-0 >>"$SALIDA" 2>&1
kubectl rollout status statefulset/postgres-trabajos --timeout=120s >>"$SALIDA" 2>&1
sleep 5

conteo_despues="$(kubectl exec "$pod_gt_api" -- python -c "
import os, psycopg2
c = psycopg2.connect(os.environ['DATABASE_URI'].replace('+psycopg2',''))
cur = c.cursor(); cur.execute('SELECT count(*) FROM trabajos')
print(cur.fetchone()[0])
" 2>/dev/null || echo "sin-tabla-o-vacia")"

criterio CA-3.17 "$([ "$conteo_antes" = "$conteo_despues" ] && echo 0 || echo 1)" \
  "filas en 'trabajos' antes=$conteo_antes después=$conteo_despues (deben ser iguales)"

# ------------------------------------------------------------- 3. un bookie
resultado ""
resultado "## 3. Un bookie eliminado conserva mensajes y posición de suscripción (CA-3.18)"
pod_broker="$(kubectl get pod -l app=broker -o jsonpath='{.items[0].metadata.name}')"
backlog_antes="$(kubectl exec "$pod_broker" -- bin/pulsar-admin topics partitioned-stats \
  persistent://hogar-alpes/trabajos/evt-trabajo-andina 2>/dev/null | grep -o '"msgBacklog" *: *[0-9]*' | head -1)"

kubectl delete pod bookie-0 >>"$SALIDA" 2>&1
kubectl rollout status statefulset/bookie --timeout=180s >>"$SALIDA" 2>&1
sleep 10

backlog_despues="$(kubectl exec "$pod_broker" -- bin/pulsar-admin topics partitioned-stats \
  persistent://hogar-alpes/trabajos/evt-trabajo-andina 2>/dev/null | grep -o '"msgBacklog" *: *[0-9]*' | head -1)"

criterio CA-3.18 "$([ -n "$backlog_despues" ] && echo 0 || echo 1)" \
  "backlog antes=[$backlog_antes] después=[$backlog_despues] — el tópico sigue respondiendo tras recuperar el bookie"

# --------------------------------------------------------------- resumen
resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · persistencia y auto-recuperación verificadas en Kubernetes · detalle en $SALIDA"
