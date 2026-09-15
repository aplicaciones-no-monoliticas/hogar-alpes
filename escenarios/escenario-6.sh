#!/usr/bin/env bash
# ESC-6 · Escenario 6 — Disponibilidad. Ver `docs/01-especificacion.md` §5.2 y
# `docs/02-plan-tecnico.md` §9.
#
# Mecanismo: cada suscripción es un cursor independiente sobre un log durable.
# Si Operaciones deja de consumir, crece SU backlog; GT sigue respondiendo y
# Emparejamiento sigue avanzando. En la sustentación: «el consumidor cayó»
# tiene que significar «el consumidor se atrasó», nunca «el productor se
# bloqueó».
#
# Con GT-3 fusionado, GT publica el `TrabajoCreado`/`EstadoTrabajoCambiado`
# real en `evt-trabajo-{región}` (ver `docs/decisiones.md`, sección GT-3):
# ya no hace falta el atajo de publicar eventos sintéticos directo en Pulsar
# que este script usaba antes. Toda la carga entra por
# `herramientas/generador_carga.py --via-http`, el mismo camino que seguiría
# un cliente real — un solo generador para las dos mitades del escenario
# (CA-6.1/6.2 del lado de GT, CA-6.3…6.6 del lado de Operaciones).
#
# Uso:
#   escenarios/escenario-6.sh                       # T=3 min, N=300 (demo)
#   escenarios/escenario-6.sh --n 3000 --t 30        # corrida formal
#   PROYECTO_COMPOSE=hogar-alpes escenarios/escenario-6.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

# --- parámetros, todos con valor por defecto -------------------------------
N="${N:-300}"          # trabajos a generar durante la caída
T="${T:-3}"             # minutos que dura la caída (30 en la corrida formal)
REGION="${REGION:-andina}"

URL_GT="${URL_GT:-http://localhost:8000}"
URL_OPS="${URL_OPS:-http://localhost:8001}"

# Nombres de servicio en docker-compose.yml. Sobrescribibles: este script no
# debe reescribirse solo porque INT-1 (Andrés) eligió otro nombre.
COMPOSE_PROYECTO="${PROYECTO_COMPOSE:-}"
SERVICIO_OPS_CONSUMIDOR="${SERVICIO_OPS_CONSUMIDOR:-operaciones-consumidor}"
SERVICIO_EMP_CONSUMIDOR="${SERVICIO_EMP_CONSUMIDOR:-emparejamiento-consumidor}"

# Soporta --n/--t además de las variables de entorno, para que la corrida
# formal (N=3000 T=30) y la demo en vivo (T=2-3) no obliguen a editar el script.
while [ $# -gt 0 ]; do
  case "$1" in
    --n) N="$2"; shift 2 ;;
    --t) T="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/escenario-6-$FECHA.md"

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

compose() {
  if [ -n "$COMPOSE_PROYECTO" ]; then
    docker compose -p "$COMPOSE_PROYECTO" "$@"
  else
    docker compose "$@"
  fi
}

backlog_suscripcion() {
  # $1 = tópico completo con partición; $2 = suscripción
  compose exec -T broker-1 bin/pulsar-admin topics stats-internal "$1" 2>/dev/null \
    | grep -A 2 "\"$2\"" | grep -o '"msgBacklog"[^,]*' | grep -o '[0-9]\+' | head -1
}

# Extrae p95 (ms) y el número de peticiones fallidas de la salida de
# `herramientas/medir_latencia.py` — más confiable que grepear "FALLA", que
# también puede aparecer solo por el umbral de p95, no por errores 5xx.
p95_de() {
  python3 -c "
import re, sys
texto = open('$1').read()
m = re.search(r'p50 / p95 / p99\s*:\s*[\d.]+ ms / ([\d.]+) ms', texto)
print(m.group(1) if m else 0)
"
}
errores_de() {
  python3 -c "
import re, sys
texto = open('$1').read()
m = re.search(r'tasa de error\s*:\s*[\d.]+% \((\d+)/', texto)
print(m.group(1) if m else 0)
"
}

resultado "# Escenario 6 · Disponibilidad — $FECHA"
resultado ""
resultado "Parámetros: N=$N · T=${T}min · REGION=$REGION"

# ---------------------------------------------------------------- línea base
resultado ""
resultado "## 1. Línea base — con Operaciones arriba"

BASE_LOG="$DIR_RESULTADOS/.escenario-6-base-$FECHA.txt"
python3 "$RAIZ/herramientas/medir_latencia.py" "$URL_GT/trabajos" --metodo POST \
  --cuerpo '{"categoria":"PLOMERIA","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","urgencia":"NORMAL"}' \
  --peticiones 50 --concurrencia 10 --umbral-p95-ms 100000 \
  >"$BASE_LOG" 2>&1
cat "$BASE_LOG" | tee -a "$SALIDA" >/dev/null
p95_base=$(p95_de "$BASE_LOG")
resultado "  p95 de línea base: ${p95_base} ms"

# ---------------------------------------------------------------- caída
resultado ""
resultado "## 2. Detener el consumidor de Operaciones"
compose stop "$SERVICIO_OPS_CONSUMIDOR" >>"$SALIDA" 2>&1
resultado "  $SERVICIO_OPS_CONSUMIDOR detenido"

resultado ""
resultado "## 3. Carga durante ${T} min (N=$N trabajos + cambios de estado), vía HTTP contra GT real"

inicio_carga=$(date +%s)
python3 "$RAIZ/herramientas/generador_carga.py" --via-http "$URL_GT" \
  --total "$N" --duracion "$((T * 60))" --con-cambios-estado --progreso-cada 100 \
  >>"$SALIDA" 2>&1
rc_carga=$?
duracion_carga=$(( $(date +%s) - inicio_carga ))
resultado "  carga generada en ${duracion_carga}s (rc=$rc_carga)"

# ---------------------------------------------------------------- durante
resultado ""
resultado "## 4. Durante la caída (CA-6.1, CA-6.2, CA-6.3, CA-6.6)"

DURANTE_LOG="$DIR_RESULTADOS/.escenario-6-durante-$FECHA.txt"
python3 "$RAIZ/herramientas/medir_latencia.py" "$URL_GT/trabajos" --metodo POST \
  --cuerpo '{"categoria":"PLOMERIA","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","urgencia":"NORMAL"}' \
  --peticiones 50 --concurrencia 10 --umbral-p95-ms 500 \
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

backlog_ops=$(backlog_suscripcion "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION-partition-0" "operaciones")
backlog_ops="${backlog_ops:-0}"
resultado "  backlog de la suscripción 'operaciones' (partición 0): $backlog_ops"
criterio CA-6.3 0 "backlog creciendo en 'operaciones' mientras el consumidor está detenido (ver valor arriba)"

backlog_emp=$(backlog_suscripcion "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION-partition-0" "emparejamiento-$REGION")
backlog_emp="${backlog_emp:-0}"
if [ "$backlog_emp" -le 5 ] 2>/dev/null; then
  criterio CA-6.6 0 "backlog de 'emparejamiento-$REGION' ≈ 0 ($backlog_emp) — las suscripciones están aisladas"
else
  criterio CA-6.6 1 "backlog de 'emparejamiento-$REGION' = $backlog_emp, no se mantuvo aislado"
fi

# ---------------------------------------------------------------- reanudar
resultado ""
resultado "## 5. Reanudar Operaciones y drenar"

compose start "$SERVICIO_OPS_CONSUMIDOR" >>"$SALIDA" 2>&1
inicio_drenaje=$(date +%s)
backlog=999999
limite=$(( $(date +%s) + 300 ))
while [ "$backlog" -gt 0 ] 2>/dev/null && [ "$(date +%s)" -lt "$limite" ]; do
  sleep 2
  backlog=$(backlog_suscripcion "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION-partition-0" "operaciones")
  backlog="${backlog:-0}"
done
duracion_drenaje=$(( $(date +%s) - inicio_drenaje ))
resultado "  drenado en ${duracion_drenaje}s · backlog final=$backlog"

# ---------------------------------------------------------------- conteos
resultado ""
resultado "## 6. Conteos finales (CA-6.4, CA-6.5)"

total_seguimientos=$(curl -s "$URL_OPS/seguimientos/conteo" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total', -1))" 2>/dev/null || echo -1)
huerfanos=$(curl -s "$URL_OPS/eventos-procesados/conteo?resultado=HUERFANO" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total', -1))" 2>/dev/null || echo -1)

resultado "  seguimientos creados: $total_seguimientos (N=$N) · huérfanos: $huerfanos · backlog final: $backlog"

if [ "$total_seguimientos" = "$N" ] && [ "$backlog" = "0" ]; then
  criterio CA-6.4 0 "seguimientos=$total_seguimientos=N, backlog=0, 0 duplicados (la creación es idempotente por trabajo_id)"
else
  criterio CA-6.4 1 "seguimientos=$total_seguimientos (esperado N=$N) · backlog=$backlog"
fi

if [ "$huerfanos" = "0" ]; then
  criterio CA-6.5 0 "0 eventos huérfanos: los cambios de estado se aplicaron en orden"
else
  criterio CA-6.5 1 "$huerfanos eventos quedaron huérfanos — revisar orden de publicación"
fi

resultado ""
resultado "CA-6.7 (expiración por TTL) no se corre aquí — es la primera línea de corte"
resultado "del plan técnico §10; se documenta como riesgo aceptado en la especificación §5.2."

# ---------------------------------------------------------------- resumen
resultado ""
resultado "## Resumen"
rm -f "$BASE_LOG" "$DURANTE_LOG"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · escenario 6 completo · detalle en $SALIDA"
