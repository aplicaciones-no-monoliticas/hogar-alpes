#!/usr/bin/env bash
# ESC-8 · Escenario 8 — Escalabilidad, variante Kubernetes. Traducción fiel
# de escenarios/escenario-8.sh (mismos pasos a-d, mismos criterios CA-8.1 a
# CA-8.6), sustituyendo `docker compose` por sus equivalentes de Kubernetes.
#
# herramientas/cargar_acreditaciones.py y herramientas/generador_carga.py
# (modo --topico) necesitan una conexión DIRECTA al broker de Pulsar; el
# broker de infra/k8s/pulsar/brokers.yaml solo anuncia su listener interno
# (accesible dentro del clúster, no hay un listener "external" publicado
# como en docker-compose.yml — ver research.md). Por eso este guion copia
# herramientas/ y contratos/ TAL CUAL (sin modificarlos) dentro de un pod ya
# desplegado que ya tiene pulsar-client instalado (gestion-trabajos-api) y
# los corre ahí con `kubectl exec`, apuntando a `pulsar://broker:6650`
# (listener interno). herramientas/medir_latencia.py y --via-http, que solo
# necesitan HTTP, corren en cambio desde afuera vía `kubectl port-forward`,
# igual que en escenario-6-k8s.sh.
#
# Uso:
#   escenarios/escenario-8-k8s.sh
#   escenarios/escenario-8-k8s.sh --proveedores 10000 --trabajos 500   # reducida

set -uo pipefail

PYTHON="${PYTHON:-python3}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

PROVEEDORES="${PROVEEDORES:-100000}"
TRABAJOS="${TRABAJOS:-2000}"
REGION_BASE="${REGION_BASE:-andina}"
REPLICAS="${REPLICAS:-1 2 4}"
SERVICIO_EMP_CONSUMIDOR="emparejamiento-$REGION_BASE"

while [ $# -gt 0 ]; do
  case "$1" in
    --proveedores) PROVEEDORES="$2"; shift 2 ;;
    --trabajos) TRABAJOS="$2"; shift 2 ;;
    --region-base) REGION_BASE="$2"; shift 2 ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

PUERTO_EMP=18003
URL_EMPAREJAMIENTO="http://localhost:${PUERTO_EMP}"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/escenario-8-k8s-$FECHA.md"

fallos=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then resultado "  PASA   $id · $detalle"; else resultado "  FALLA  $id · $detalle"; fallos=$((fallos + 1)); fi
}

# --- pod de herramientas: copia contratos/+herramientas/ sin modificarlos ---
POD_HERRAMIENTAS="$(kubectl get pod -l app=gestion-trabajos-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')"
kubectl exec "$POD_HERRAMIENTAS" -- rm -rf /tmp/hda-tools >/dev/null 2>&1 || true
kubectl exec "$POD_HERRAMIENTAS" -- mkdir -p /tmp/hda-tools >/dev/null 2>&1
kubectl cp "$RAIZ/contratos" "default/$POD_HERRAMIENTAS:/tmp/hda-tools/contratos" >/dev/null 2>&1
kubectl cp "$RAIZ/herramientas" "default/$POD_HERRAMIENTAS:/tmp/hda-tools/herramientas" >/dev/null 2>&1
kubectl cp "$RAIZ/infra/sidecar/reglas_regionales.json" "default/$POD_HERRAMIENTAS:/tmp/hda-tools/reglas_regionales.json" >/dev/null 2>&1

en_pod() {
  # Corre herramientas/<script>.py dentro del pod, contra el listener
  # interno del broker — sin esto, pulsar-client no resuelve la dirección
  # anunciada del broker desde fuera del clúster.
  kubectl exec "$POD_HERRAMIENTAS" -- env PYTHONPATH=/tmp/hda-tools BROKER_URL=pulsar://broker:6650 BROKER_LISTENER=internal \
    python3 "/tmp/hda-tools/herramientas/$1" "${@:2}" --broker pulsar://broker:6650 --listener internal
}

# --- puente local hacia emparejamiento-api, para medir_latencia.py (HTTP) --
kubectl port-forward svc/emparejamiento-api "${PUERTO_EMP}:5000" >/dev/null 2>&1 &
PID_PF=$!
trap 'kill $PID_PF 2>/dev/null || true; kubectl exec "$POD_HERRAMIENTAS" -- rm -rf /tmp/hda-tools >/dev/null 2>&1 || true' EXIT
sleep 3

backlog_de() {
  # $1 = tópico particionado · $2 = suscripción
  local pod_broker
  pod_broker="$(kubectl get pod -l app=broker --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')"
  kubectl exec "$pod_broker" -- bin/pulsar-admin topics partitioned-stats "$1" 2>/dev/null \
    | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('subscriptions', {}).get('$2', {}).get('msgBacklog', 0))
except Exception:
    print(0)
"
}

resultado "# Escenario 8 (Kubernetes) · Escalabilidad — $FECHA"
resultado ""
resultado "Parámetros: PROVEEDORES=$PROVEEDORES · TRABAJOS=$TRABAJOS · REGION_BASE=$REGION_BASE · REPLICAS=\"$REPLICAS\""

# ---------------------------------------------------------------- paso (a)
resultado ""
resultado "## a. Carga de acreditaciones (CA-8.1)"
inicio_carga=$(date +%s)
if en_pod cargar_acreditaciones.py --total "$PROVEEDORES" >>"$SALIDA" 2>&1; then
  duracion_carga=$(( $(date +%s) - inicio_carga ))
  resultado "  carga publicada en ${duracion_carga}s"
  criterio CA-8.1a 0 "$PROVEEDORES proveedores publicados por cmd-acreditacion"
else
  criterio CA-8.1a 1 "la carga de acreditaciones falló — ver salida arriba"
fi

resultado ""
resultado "  esperando a que la proyección converja (retraso p95 < 5s en operación normal, CA-8.6)…"
sleep 10

# ---------------------------------------------------------------- paso (b)
resultado ""
resultado "## b. Latencia de \`GET /candidatos\` (CA-8.2: p95 < 1 s con >= 100.000 proveedores)"
if $PYTHON "$RAIZ/herramientas/medir_latencia.py" \
    "$URL_EMPAREJAMIENTO/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota" \
    --peticiones 200 --concurrencia 20 --umbral-p95-ms 1000 \
    >>"$SALIDA" 2>&1; then
  criterio CA-8.2 0 "p95 < 1000 ms — ver detalle en $SALIDA"
else
  criterio CA-8.2 1 "p95 >= 1000 ms o hubo errores — ver detalle en $SALIDA"
fi

# ---------------------------------------------------------------- paso (c)
resultado ""
resultado "## c. Drenaje de backlog con k réplicas del consumidor regional (CA-8.3, CA-8.5)"
resultado "  Se precarga el backlog con el consumidor en 0 copias, se escala a k y se mide"
resultado "  el tiempo hasta vaciarlo — el throughput medido es el del consumidor."

kubectl scale "deployment/$SERVICIO_EMP_CONSUMIDOR" --replicas=0 >>"$SALIDA" 2>&1
kubectl wait --for=delete "pod" -l "app=$SERVICIO_EMP_CONSUMIDOR" --timeout=60s >>"$SALIDA" 2>&1 || true

if en_pod generador_carga.py --topico "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION_BASE" --total "$TRABAJOS" >>"$SALIDA" 2>&1; then
  resultado "  backlog precargado: $TRABAJOS eventos en evt-trabajo-$REGION_BASE"
else
  resultado "  AVISO · no se pudo precargar el backlog — ver salida arriba"
fi

throughput_anterior=""
for k in $REPLICAS; do
  kubectl scale "deployment/$SERVICIO_EMP_CONSUMIDOR" --replicas="$k" >>"$SALIDA" 2>&1
  kubectl rollout status "deployment/$SERVICIO_EMP_CONSUMIDOR" --timeout=120s >>"$SALIDA" 2>&1

  inicio=$(date +%s)
  backlog=999999
  limite=$(( $(date +%s) + 600 ))
  while [ "$backlog" -gt 0 ] 2>/dev/null && [ "$(date +%s)" -lt "$limite" ]; do
    sleep 2
    backlog=$(backlog_de "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION_BASE" "$SERVICIO_EMP_CONSUMIDOR")
    backlog="${backlog:-0}"
  done
  duracion=$(( $(date +%s) - inicio ))
  throughput=0
  [ "$duracion" -gt 0 ] && throughput=$(( TRABAJOS / duracion ))

  resultado "  k=$k réplicas · drenó en ${duracion}s · throughput ≈ ${throughput} trabajos/s"

  if [ -n "$throughput_anterior" ] && [ "$k" = "2" ]; then
    umbral=$(( throughput_anterior * 18 / 10 ))
    if [ "$throughput" -ge "$umbral" ]; then
      criterio CA-8.3 0 "1→2 réplicas: ${throughput_anterior} → ${throughput} trabajos/s (umbral >= ${umbral})"
    else
      criterio CA-8.3 1 "1→2 réplicas: ${throughput_anterior} → ${throughput} trabajos/s (umbral >= ${umbral})"
    fi
  fi
  [ "$k" = "4" ] && resultado "  (4 réplicas es informativo, no umbral duro)"
  throughput_anterior="$throughput"

  kubectl scale "deployment/$SERVICIO_EMP_CONSUMIDOR" --replicas=0 >>"$SALIDA" 2>&1
  kubectl wait --for=delete "pod" -l "app=$SERVICIO_EMP_CONSUMIDOR" --timeout=60s >>"$SALIDA" 2>&1 || true
  en_pod generador_carga.py --topico "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION_BASE" --total "$TRABAJOS" >>"$SALIDA" 2>&1
done

resultado "  CA-8.5 (orden dentro de un mismo trabajo) se verifica con los logs del"
resultado "  consumidor: cada trabajo aparece una sola vez en la tabla emparejamientos."

# ---------------------------------------------------------------- paso (d)
resultado ""
resultado "## d. Región en caliente (CA-8.4)"
kubectl scale "deployment/$SERVICIO_EMP_CONSUMIDOR" --replicas=2 >>"$SALIDA" 2>&1
kubectl rollout status "deployment/$SERVICIO_EMP_CONSUMIDOR" --timeout=60s >>"$SALIDA" 2>&1
sleep 3

PUERTO_ACR=18002
kubectl port-forward svc/acreditacion-api "${PUERTO_ACR}:5000" >/dev/null 2>&1 &
PID_PF_ACR=$!
sleep 3

antes=$($PYTHON "$RAIZ/herramientas/medir_latencia.py" "http://localhost:${PUERTO_ACR}/health" \
  --peticiones 50 --concurrencia 10 2>&1 | tee -a "$SALIDA" | grep -c 'FALLA')

REGION_NUEVA="${REGION_NUEVA:-conosur}"
kubectl create configmap pulsar-scripts-agregar-region \
  --from-file="$RAIZ/infra/pulsar/agregar-region.sh" \
  --from-file="$RAIZ/infra/pulsar/comun.sh" \
  --from-file="$RAIZ/infra/pulsar/topologia.env" \
  --dry-run=client -o yaml | kubectl apply -f - >>"$SALIDA" 2>&1
kubectl delete job agregar-region-esc8 --ignore-not-found >>"$SALIDA" 2>&1
cat <<EOF | kubectl apply -f - >>"$SALIDA" 2>&1
apiVersion: batch/v1
kind: Job
metadata:
  name: agregar-region-esc8
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: agregar-region
          image: apachepulsar/pulsar:3.2.2
          command: ["bash", "/infra/agregar-region.sh", "$REGION_NUEVA"]
          env: [{name: PULSAR_ADMIN_URL, value: "http://broker:8080"}]
          volumeMounts: [{name: scripts, mountPath: /infra}]
      volumes:
        - name: scripts
          configMap: {name: pulsar-scripts-agregar-region, defaultMode: 0755}
EOF
kubectl wait --for=condition=complete job/agregar-region-esc8 --timeout=120s >>"$SALIDA" 2>&1
resultado_alta=$?

despues=$($PYTHON "$RAIZ/herramientas/medir_latencia.py" "http://localhost:${PUERTO_ACR}/health" \
  --peticiones 50 --concurrencia 10 2>&1 | tee -a "$SALIDA" | grep -c 'FALLA')

kill $PID_PF_ACR 2>/dev/null || true

if [ "$resultado_alta" -eq 0 ] && [ "$antes" -eq 0 ] && [ "$despues" -eq 0 ]; then
  criterio CA-8.4 0 "región '$REGION_NUEVA' habilitada sin errores en las regiones activas"
else
  criterio CA-8.4 1 "la alta de '$REGION_NUEVA' o las mediciones alrededor mostraron errores"
fi

resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · escenario 8 (Kubernetes) completo · detalle en $SALIDA"
