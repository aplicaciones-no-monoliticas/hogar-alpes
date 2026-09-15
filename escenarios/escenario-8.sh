#!/usr/bin/env bash
# ESC-8 · Escenario 8 — Escalabilidad. Ver `docs/01-especificacion.md` §5.3 y
# `docs/02-plan-tecnico.md` §9 (procedimiento a-d) y §10 (líneas de corte).
#
# No prueba el número de producción (15.600 req/s): prueba la PROPIEDAD que
# promete la decisión arquitectural — el throughput crece de forma
# aproximadamente lineal al agregar réplicas, una región nueva no interrumpe a
# las activas, y la consulta de candidatos responde en < 1 s con >= 100.000
# proveedores. En la sustentación: no probamos el número, probamos la
# pendiente (spec §2).
#
# Pasos (los mismos a-d del plan técnico):
#   a. Cargar <PROVEEDORES> acreditaciones por `cmd-acreditacion` (HER-3) y
#      medir el retraso de la proyección.
#   b. Latencia de `GET /candidatos` con combinaciones reales (HER-2) — CA-8.2.
#   c. Precargar un backlog de <TRABAJOS> `TrabajoCreado` en la región base y
#      drenarlo con k = 1, 2 y 4 réplicas del consumidor REGIONAL de
#      Emparejamiento — CA-8.3, CA-8.5.
#   d. Con carga sostenida en la región base, habilitar una región nueva
#      (`infra/pulsar/agregar-region.sh`) y medir throughput/errores de la
#      región base antes, durante y después — CA-8.4.
#
# Requiere el sistema arriba (`docker compose up -d`) con Pulsar y los cuatro
# servicios sanos. Los nombres de servicio de Compose son los que fija INT-1;
# si difieren de los valores por defecto de abajo, sobrescríbalos por entorno.
#
# Uso:
#   escenarios/escenario-8.sh
#   escenarios/escenario-8.sh --proveedores 10000 --trabajos 500   # corrida reducida (recomendada para depurar)
#   PROYECTO_COMPOSE=hogar-alpes escenarios/escenario-8.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

# --- parámetros, todos con valor por defecto -------------------------------
PROVEEDORES="${PROVEEDORES:-100000}"
TRABAJOS="${TRABAJOS:-2000}"
REGION_BASE="${REGION_BASE:-andina}"
REGION_NUEVA="${REGION_NUEVA:-conosur}"
REPLICAS="${REPLICAS:-1 2 4}"

# La cabecera de este script documenta `--proveedores`/`--trabajos` (línea
# 29) pero no existía ningún parseo de argumentos: se ignoraban en silencio y
# la corrida "reducida para depurar" en realidad corría con los 100.000/2.000
# de siempre.
while [ $# -gt 0 ]; do
  case "$1" in
    --proveedores) PROVEEDORES="$2"; shift 2 ;;
    --trabajos) TRABAJOS="$2"; shift 2 ;;
    --region-base) REGION_BASE="$2"; shift 2 ;;
    --region-nueva) REGION_NUEVA="$2"; shift 2 ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

URL_ACREDITACION="${URL_ACREDITACION:-http://localhost:8002}"
URL_EMPAREJAMIENTO="${URL_EMPAREJAMIENTO:-http://localhost:8003}"
BROKER_URL="${BROKER_URL:-pulsar://localhost:6650}"
BROKER_LISTENER="${BROKER_LISTENER:-external}"

# Nombres de servicio en docker-compose.yml (INT-1). Sobrescribibles: este
# script no debe reescribirse solo porque INT-1 eligió otro nombre.
#
# El consumidor regional de Emparejamiento se llama `emparejamiento-<región>`
# (una réplica por región, no un solo "-consumidor" genérico — ver
# docker-compose.yml y el README de emparejamiento): con REGION_BASE=andina
# el servicio real es `emparejamiento-andina`, no `emparejamiento-consumidor`
# (ese nombre no existe y `docker compose stop/up` fallaba con
# "no such service" en cada paso de c y d).
COMPOSE_PROYECTO="${PROYECTO_COMPOSE:-}"
SERVICIO_EMP_CONSUMIDOR="${SERVICIO_EMP_CONSUMIDOR:-emparejamiento-$REGION_BASE}"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/escenario-8-$FECHA.md"

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

resultado "# Escenario 8 · Escalabilidad — $FECHA"
resultado ""
resultado "Parámetros: PROVEEDORES=$PROVEEDORES · TRABAJOS=$TRABAJOS · REGION_BASE=$REGION_BASE · REGION_NUEVA=$REGION_NUEVA · REPLICAS=\"$REPLICAS\""

# ---------------------------------------------------------------- paso (a)
resultado ""
resultado "## a. Carga de acreditaciones (CA-8.1)"

inicio_carga=$(date +%s)
if python3 "$RAIZ/herramientas/cargar_acreditaciones.py" \
    --total "$PROVEEDORES" --broker "$BROKER_URL" --listener "$BROKER_LISTENER" \
    >>"$SALIDA" 2>&1; then
  duracion_carga=$(( $(date +%s) - inicio_carga ))
  resultado "  carga publicada en ${duracion_carga}s"
  criterio CA-8.1a 0 "$PROVEEDORES proveedores publicados por cmd-acreditacion"
else
  criterio CA-8.1a 1 "la carga de acreditaciones falló — ver salida arriba"
fi

# Retraso de la proyección: se espera a que se estabilice el conteo antes de
# medir consultas (evita medir contra una proyección todavía incompleta).
resultado ""
resultado "  esperando a que la proyección converja (retraso p95 < 5s en operación normal, CA-8.6)…"
sleep 10

# ---------------------------------------------------------------- paso (b)
resultado ""
resultado "## b. Latencia de \`GET /candidatos\` (CA-8.2: p95 < 1 s con >= 100.000 proveedores)"

if python3 "$RAIZ/herramientas/medir_latencia.py" \
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
resultado "  Se precarga el backlog con el consumidor DETENIDO (réplicas=0), se conecta"
resultado "  k réplicas y se mide el tiempo hasta vaciarlo — así el throughput medido es"
resultado "  el del consumidor, no el de la conexión (riesgo RT-4 del plan técnico)."

compose stop "$SERVICIO_EMP_CONSUMIDOR" >>"$SALIDA" 2>&1

if python3 "$RAIZ/herramientas/generador_carga.py" \
    --topico "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION_BASE" \
    --total "$TRABAJOS" --broker "$BROKER_URL" --listener "$BROKER_LISTENER" \
    >>"$SALIDA" 2>&1; then
  resultado "  backlog precargado: $TRABAJOS eventos en evt-trabajo-$REGION_BASE"
else
  resultado "  AVISO · no se pudo precargar con herramientas/generador_carga.py (¿existe todavía? es de HER-1, Stiven)"
fi

throughput_anterior=""
for k in $REPLICAS; do
  compose up -d --scale "$SERVICIO_EMP_CONSUMIDOR=$k" "$SERVICIO_EMP_CONSUMIDOR" >>"$SALIDA" 2>&1

  inicio=$(date +%s)
  backlog=999999
  limite=$(( $(date +%s) + 600 ))
  while [ "$backlog" -gt 0 ] && [ "$(date +%s)" -lt "$limite" ]; do
    sleep 2
    # `partitioned-stats` agrega las 4 particiones. Mirar solo la partición 0
    # (como hacía esta línea) subestima el backlog real: con trabajo_id como
    # clave, GT reparte los TrabajoCreado entre las 4, así que "drenó" se
    # declaraba en cuanto la partición 0 vaciaba —casi de inmediato, aunque
    # 1-3 siguieran llenas— y el throughput medido no tenía nada que ver con
    # cuántas réplicas estaban realmente consumiendo (por eso 1→2→4 daba
    # 400→333→333: no escalaba porque no se estaba midiendo el drenaje real).
    backlog=$(
      compose exec -T broker-1 bin/pulsar-admin topics partitioned-stats \
        "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION_BASE" 2>/dev/null \
      | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('subscriptions', {}).get('emparejamiento-$REGION_BASE', {}).get('msgBacklog', 0))
except Exception:
    print(0)
"
    )
    backlog="${backlog:-0}"
  done
  duracion=$(( $(date +%s) - inicio ))
  throughput=0
  [ "$duracion" -gt 0 ] && throughput=$(( TRABAJOS / duracion ))

  resultado "  k=$k réplicas · drenó en ${duracion}s · throughput ≈ ${throughput} trabajos/s"

  if [ -n "$throughput_anterior" ] && [ "$k" = "2" ]; then
    # CA-8.3: throughput con 2 réplicas >= 1.8x el de 1 réplica (degradación < 10%)
    umbral=$(( throughput_anterior * 18 / 10 ))
    if [ "$throughput" -ge "$umbral" ]; then
      criterio CA-8.3 0 "1→2 réplicas: ${throughput_anterior} → ${throughput} trabajos/s (umbral >= ${umbral})"
    else
      criterio CA-8.3 1 "1→2 réplicas: ${throughput_anterior} → ${throughput} trabajos/s (umbral >= ${umbral})"
    fi
  fi
  [ "$k" = "4" ] && resultado "  (4 réplicas es informativo — R-2 del plan técnico, no umbral duro)"
  throughput_anterior="$throughput"

  # Recarga el backlog para la siguiente k, con el consumidor detenido de nuevo.
  compose stop "$SERVICIO_EMP_CONSUMIDOR" >>"$SALIDA" 2>&1
  python3 "$RAIZ/herramientas/generador_carga.py" \
    --topico "persistent://hogar-alpes/trabajos/evt-trabajo-$REGION_BASE" \
    --total "$TRABAJOS" --broker "$BROKER_URL" --listener "$BROKER_LISTENER" \
    >>"$SALIDA" 2>&1
done

resultado "  CA-8.5 (orden dentro de un mismo trabajo) se verifica con los logs del"
resultado "  consumidor: cada trabajo aparece una sola vez en la tabla emparejamientos,"
resultado "  sin aplicar un EstadoTrabajoCambiado antes que su TrabajoCreado."

# ---------------------------------------------------------------- paso (d)
resultado ""
resultado "## d. Región en caliente (CA-8.4)"

compose up -d --scale "$SERVICIO_EMP_CONSUMIDOR=2" "$SERVICIO_EMP_CONSUMIDOR" >>"$SALIDA" 2>&1
sleep 3

antes=$(python3 "$RAIZ/herramientas/medir_latencia.py" "$URL_ACREDITACION/health" \
  --peticiones 50 --concurrencia 10 2>&1 | tee -a "$SALIDA" | grep -c 'FALLA')

# agregar-region.sh corre `pulsar-admin` desde /pulsar/bin (comun.sh), que
# solo existe DENTRO de la imagen de Pulsar — invocarlo con `bash` directo en
# el host (como hacía esta línea, con PULSAR_ADMIN_URL apuntando al puerto
# publicado) fallaba con "/pulsar/bin/pulsar-admin: No such file or
# directory". Va por `docker compose run`, igual que documenta la cabecera
# del propio agregar-region.sh y que ya usa el resto del repo.
compose run --rm pulsar-config bash /infra/agregar-region.sh "$REGION_NUEVA" \
  >>"$SALIDA" 2>&1
resultado_alta=$?

despues=$(python3 "$RAIZ/herramientas/medir_latencia.py" "$URL_ACREDITACION/health" \
  --peticiones 50 --concurrencia 10 2>&1 | tee -a "$SALIDA" | grep -c 'FALLA')

if [ "$resultado_alta" -eq 0 ] && [ "$antes" -eq 0 ] && [ "$despues" -eq 0 ]; then
  criterio CA-8.4 0 "región '$REGION_NUEVA' habilitada sin errores en las regiones activas"
else
  criterio CA-8.4 1 "la alta de '$REGION_NUEVA' o las mediciones alrededor mostraron errores"
fi

# ---------------------------------------------------------------- resumen
resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · escenario 8 completo · detalle en $SALIDA"
