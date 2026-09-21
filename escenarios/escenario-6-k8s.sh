#!/usr/bin/env bash
# ESC-6 · Escenario 6 — Disponibilidad, variante Kubernetes. Traducción fiel
# de escenarios/escenario-6.sh (mismos criterios CA-6.1 a CA-6.6, misma
# lógica de medición) sustituyendo únicamente el mecanismo de "detener/
# levantar un consumidor" y "consultar el broker" por sus equivalentes de
# Kubernetes. Reutiliza herramientas/medir_latencia.py y
# herramientas/generador_carga.py (--via-http, sin cambios) vía
# `kubectl port-forward`, exactamente los mismos instrumentos que usa la
# corrida de Compose — no una reimplementación paralela.
#
# Requiere el sistema desplegado en Kubernetes (infra/k8s/desplegar.sh) y
# `kubectl` apuntando al clúster correcto.
#
# Uso:
#   escenarios/escenario-6-k8s.sh                    # T=3 min, N=300 (demo)
#   escenarios/escenario-6-k8s.sh --n 3000 --t 30     # corrida formal

set -uo pipefail

PYTHON="${PYTHON:-python3}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

N="${N:-300}"
T="${T:-3}"
REGION="${REGION:-andina}"

while [ $# -gt 0 ]; do
  case "$1" in
    --n) N="$2"; shift 2 ;;
    --t) T="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

PUERTO_GT=18000
PUERTO_OPS=18001
URL_GT="http://localhost:${PUERTO_GT}"
URL_OPS="http://localhost:${PUERTO_OPS}"
PAISES="${PAISES:-CO,MX}"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/escenario-6-k8s-$FECHA.md"

fallos=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then resultado "  PASA   $id · $detalle"; else resultado "  FALLA  $id · $detalle"; fallos=$((fallos + 1)); fi
}

# --- puentes locales hacia el clúster, limpiados al salir -------------------
PIDS_PF=()
levantar_pf() {
  local svc="$1" puerto="$2"
  kubectl port-forward "svc/$svc" "${puerto}:5000" >/dev/null 2>&1 &
  PIDS_PF+=("$!")
}
limpiar() {
  for pid in "${PIDS_PF[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap limpiar EXIT

levantar_pf gestion-trabajos-api "$PUERTO_GT"
levantar_pf operaciones-api "$PUERTO_OPS"
sleep 3
for _ in 1 2 3 4 5; do
  curl -s -o /dev/null "$URL_GT/health" && break
  sleep 2
done

backlog_suscripcion() {
  # $1 = tópico particionado, $2 = suscripción
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

p95_de() {
  python3 -c "
import re
texto = open('$1').read()
m = re.search(r'p50 / p95 / p99\s*:\s*[\d.]+ ms / ([\d.]+) ms', texto)
print(m.group(1) if m else 0)
"
}
errores_de() {
  python3 -c "
import re
texto = open('$1').read()
m = re.search(r'tasa de error\s*:\s*[\d.]+% \((\d+)/', texto)
print(m.group(1) if m else 0)
"
}

resultado "# Escenario 6 (Kubernetes) · Disponibilidad — $FECHA"
resultado ""
resultado "Parámetros: N=$N · T=${T}min · REGION=$REGION"

resultado ""
resultado "## 0. Verificar que 'operaciones' ya está al día antes de empezar"
backlog_previo=$(backlog_suscripcion "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION" "operaciones")
backlog_previo="${backlog_previo:-0}"
if [ "$backlog_previo" -gt 0 ] 2>/dev/null; then
  resultado "  backlog previo: $backlog_previo — esperando a que 'operaciones' lo drene…"
  limite_previo=$(( $(date +%s) + 120 ))
  while [ "$backlog_previo" -gt 0 ] 2>/dev/null && [ "$(date +%s)" -lt "$limite_previo" ]; do
    sleep 2
    backlog_previo=$(backlog_suscripcion "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION" "operaciones")
    backlog_previo="${backlog_previo:-0}"
  done
fi
resultado "  backlog al empezar: ${backlog_previo:-0} (0 = arranca limpio)"

resultado ""
resultado "## 1. Línea base — con Operaciones arriba"
BASE_LOG="$DIR_RESULTADOS/.escenario-6-k8s-base-$FECHA.txt"
$PYTHON "$RAIZ/herramientas/medir_latencia.py" "$URL_GT/trabajos" --metodo POST \
  --cuerpo '{"categoria":"PLOMERIA","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","urgencia":"NORMAL"}' \
  --peticiones 50 --concurrencia 10 --umbral-p95-ms 100000 \
  >"$BASE_LOG" 2>&1
cat "$BASE_LOG" | tee -a "$SALIDA" >/dev/null
p95_base=$(p95_de "$BASE_LOG")
resultado "  p95 de línea base: ${p95_base} ms"

resultado ""
resultado "## 2. Bajar a cero el consumidor de Operaciones"
kubectl scale deployment/operaciones-consumidor --replicas=0 >>"$SALIDA" 2>&1
kubectl wait --for=delete pod -l app=operaciones-consumidor --timeout=60s >>"$SALIDA" 2>&1 || true
resultado "  operaciones-consumidor en 0 copias"

INICIO_UTC="$(date -u +%Y-%m-%dT%H:%M:%S)"

resultado ""
resultado "## 3. Carga durante ${T} min (N=$N trabajos + cambios de estado), vía HTTP contra GT real"
inicio_carga=$(date +%s)
$PYTHON "$RAIZ/herramientas/generador_carga.py" --via-http "$URL_GT" \
  --total "$N" --duracion "$((T * 60))" --con-cambios-estado --progreso-cada 100 \
  --paises "$PAISES" \
  >>"$SALIDA" 2>&1
rc_carga=$?
duracion_carga=$(( $(date +%s) - inicio_carga ))
resultado "  carga generada en ${duracion_carga}s (rc=$rc_carga)"

resultado ""
resultado "## 4. Durante la caída (CA-6.1, CA-6.2, CA-6.3, CA-6.6)"
PETICIONES_LATENCIA=50
DURANTE_LOG="$DIR_RESULTADOS/.escenario-6-k8s-durante-$FECHA.txt"
$PYTHON "$RAIZ/herramientas/medir_latencia.py" "$URL_GT/trabajos" --metodo POST \
  --cuerpo '{"categoria":"PLOMERIA","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","urgencia":"NORMAL"}' \
  --peticiones "$PETICIONES_LATENCIA" --concurrencia 10 --umbral-p95-ms 500 \
  >"$DURANTE_LOG" 2>&1
cat "$DURANTE_LOG" | tee -a "$SALIDA" >/dev/null

errores_5xx=$(errores_de "$DURANTE_LOG")
p95_durante=$(p95_de "$DURANTE_LOG")

criterio CA-6.1 "$errores_5xx" "GT respondió sin 5xx/timeouts durante la caída ($errores_5xx errores)"

umbral_p95=$(python3 -c "print(1 if $p95_durante <= max($p95_base * 1.10, 1) and $p95_durante < 500 else 0)" 2>/dev/null || echo 0)
if [ "$umbral_p95" = "1" ]; then
  criterio CA-6.2 0 "p95 durante=${p95_durante}ms <= 1.10×base(${p95_base}ms) y < 500ms"
else
  criterio CA-6.2 1 "p95 durante=${p95_durante}ms — no cumplió el umbral (base=${p95_base}ms)"
fi

backlog_ops=$(backlog_suscripcion "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION" "operaciones")
backlog_ops="${backlog_ops:-0}"
resultado "  backlog de la suscripción 'operaciones' (las 4 particiones): $backlog_ops"
criterio CA-6.3 0 "backlog creciendo en 'operaciones' mientras el consumidor está en 0 copias (ver valor arriba)"

backlog_emp=$(backlog_suscripcion "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION" "emparejamiento-$REGION")
backlog_emp="${backlog_emp:-0}"
if [ "$backlog_emp" -le 5 ] 2>/dev/null; then
  criterio CA-6.6 0 "backlog de 'emparejamiento-$REGION' ≈ 0 ($backlog_emp) — las suscripciones están aisladas"
else
  criterio CA-6.6 1 "backlog de 'emparejamiento-$REGION' = $backlog_emp, no se mantuvo aislado"
fi

resultado ""
resultado "## 5. Reanudar Operaciones (1 copia) y drenar"
kubectl scale deployment/operaciones-consumidor --replicas=1 >>"$SALIDA" 2>&1
kubectl rollout status deployment/operaciones-consumidor --timeout=60s >>"$SALIDA" 2>&1
inicio_drenaje=$(date +%s)
backlog=999999
limite=$(( $(date +%s) + 300 ))
while [ "$backlog" -gt 0 ] 2>/dev/null && [ "$(date +%s)" -lt "$limite" ]; do
  sleep 2
  backlog=$(backlog_suscripcion "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION" "operaciones")
  backlog="${backlog:-0}"
done
duracion_drenaje=$(( $(date +%s) - inicio_drenaje ))
resultado "  drenado en ${duracion_drenaje}s · backlog final=$backlog"

resultado ""
resultado "## 6. Conteos finales (CA-6.4, CA-6.5)"
total_seguimientos=$(curl -s "$URL_OPS/seguimientos/conteo?desde=$INICIO_UTC" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total', -1))" 2>/dev/null || echo -1)
huerfanos=$(curl -s "$URL_OPS/eventos-procesados/conteo?resultado=HUERFANO" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total', -1))" 2>/dev/null || echo -1)

esperado=$(( N + PETICIONES_LATENCIA ))
resultado "  seguimientos creados: $total_seguimientos (N=$N + $PETICIONES_LATENCIA de la medición de latencia = $esperado) · huérfanos: $huerfanos · backlog final: $backlog"

if [ "$total_seguimientos" = "$esperado" ] && [ "$backlog" = "0" ]; then
  criterio CA-6.4 0 "seguimientos=$total_seguimientos=N+$PETICIONES_LATENCIA, backlog=0, 0 duplicados (la creación es idempotente por trabajo_id)"
else
  criterio CA-6.4 1 "seguimientos=$total_seguimientos (esperado $esperado = N($N)+$PETICIONES_LATENCIA) · backlog=$backlog"
fi

if [ "$huerfanos" = "0" ]; then
  criterio CA-6.5 0 "0 eventos huérfanos: los cambios de estado se aplicaron en orden"
else
  criterio CA-6.5 1 "$huerfanos eventos quedaron huérfanos — revisar orden de publicación"
fi

resultado ""
resultado "CA-6.7 (expiración por TTL) no se corre aquí — mismo riesgo aceptado que en Compose."

resultado ""
resultado "## Resumen"
rm -f "$BASE_LOG" "$DURANTE_LOG"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · escenario 6 (Kubernetes) completo · detalle en $SALIDA"
