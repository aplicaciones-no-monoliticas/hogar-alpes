#!/usr/bin/env bash
# Saga de asignación de un trabajo (Entrega 5) — los cuatro casos de
# `specs/002-saga-asignacion-trabajo/quickstart.md`, releídos del broker/DB
# (Principio VI): cada aserción compara contra lo que devuelven `gestion-trabajos`
# y `saga-log` después de dejar correr la saga, nunca contra lo que el propio
# script acaba de enviar.
#
#   docker compose up -d --build
#   bash escenarios/saga.sh
#
# Requiere al menos un proveedor ACREDITADA y vigente cargado para el Caso 1
# (ver quickstart.md · Prerrequisitos). Si no hay ninguno, el Caso 1 falla con
# un mensaje explícito en vez de un PASA falso.

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

URL_BFF="${URL_BFF:-http://localhost:8090}"
URL_GT="${URL_GT:-http://localhost:8000}"
URL_SAGA="${URL_SAGA:-http://localhost:8004}"
CATEGORIA="${CATEGORIA_PRUEBA:-PLOMERIA}"
ESPERA_MAX_S="${ESPERA_MAX_S:-30}"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/saga-$FECHA.md"

INICIO_EPOCH=$(date +%s)
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

crear_trabajo() {
  local simular_fallo="$1"
  local cuerpo
  if [ -n "$simular_fallo" ]; then
    cuerpo=$(printf '{"categoria":"%s","urgencia":"NORMAL","pais":"CO","ciudad":"Bogota","direccion":"Calle 1","descripcion":"saga.sh","partner_id":"demo","simular_fallo":"%s"}' "$CATEGORIA" "$simular_fallo")
  else
    cuerpo=$(printf '{"categoria":"%s","urgencia":"NORMAL","pais":"CO","ciudad":"Bogota","direccion":"Calle 1","descripcion":"saga.sh","partner_id":"demo"}' "$CATEGORIA")
  fi
  curl -s -X POST "$URL_BFF/trabajos/asignacion" -H 'Content-Type: application/json' -d "$cuerpo"
}

trabajo_id_de() {
  python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("id",""))
except Exception: print("")' 2>/dev/null
}

campo_trabajo() {
  local trabajo_id="$1" campo="$2"
  curl -s "$URL_GT/trabajos/$trabajo_id" | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('$campo','') or '')
except Exception: print('')" 2>/dev/null
}

esperar_estado_final() {
  # Espera hasta ESPERA_MAX_S a que GT reporte ASIGNADO o CANCELADO.
  local trabajo_id="$1" estado=""
  for _ in $(seq 1 "$ESPERA_MAX_S"); do
    estado="$(campo_trabajo "$trabajo_id" estado)"
    case "$estado" in
      ASIGNADO|CANCELADO) echo "$estado"; return 0 ;;
    esac
    sleep 1
  done
  echo "$estado"
}

saga_de() {
  curl -s "$URL_SAGA/sagas/$1"
}

campo_saga() {
  local trabajo_id="$1" campo="$2"
  saga_de "$trabajo_id" | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('$campo',''))
except Exception: print('')" 2>/dev/null
}

pasos_de() {
  saga_de "$1" | python3 -c 'import json,sys
try:
    for p in json.load(sys.stdin).get("pasos", []):
        print(p["direccion"], p["paso"])
except Exception:
    pass' 2>/dev/null
}

resultado "# Saga de asignación de un trabajo — $FECHA"
resultado ""
resultado "URL_BFF=$URL_BFF · URL_GT=$URL_GT · URL_SAGA=$URL_SAGA · CATEGORIA=$CATEGORIA"

# ------------------------------------------------------------- Caso 1 (CA-1.1/1.2)
resultado ""
resultado "## Caso 1 — Camino feliz"

respuesta1="$(crear_trabajo '')"
t1="$(echo "$respuesta1" | trabajo_id_de)"
if [ -z "$t1" ]; then
  criterio CASO-1a 1 "no se pudo crear el trabajo: $respuesta1"
else
  estado1="$(esperar_estado_final "$t1")"
  proveedor1="$(campo_trabajo "$t1" proveedor_id)"
  criterio CASO-1a "$([ "$estado1" = ASIGNADO ] && echo 0 || echo 1)" \
    "GET /trabajos/$t1 -> estado=$estado1 (esperado ASIGNADO; si no hay proveedores ACREDITADA vigentes cargados, este caso falla — ver Prerrequisitos de quickstart.md)"
  criterio CASO-1b "$([ -n "$proveedor1" ] && echo 0 || echo 1)" \
    "GET /trabajos/$t1 -> proveedor_id=$proveedor1 (esperado no vacío)"

  estado_saga1="$(campo_saga "$t1" estado)"
  n_pasos1="$(pasos_de "$t1" | wc -l | tr -d ' ')"
  criterio CASO-1c "$([ "$estado_saga1" = COMPLETADA ] && echo 0 || echo 1)" \
    "GET /sagas/$t1 -> estado=$estado_saga1 (esperado COMPLETADA)"
  criterio CASO-1d "$([ "$n_pasos1" = 4 ] && echo 0 || echo 1)" \
    "GET /sagas/$t1 -> ${n_pasos1} paso(s) (esperados 4)"
fi

# ------------------------------------------------------------- Caso 2 (CA-1.3)
resultado ""
resultado "## Caso 2 — simular_fallo=VIGENCIA"

respuesta2="$(crear_trabajo VIGENCIA)"
t2="$(echo "$respuesta2" | trabajo_id_de)"
if [ -z "$t2" ]; then
  criterio CASO-2a 1 "no se pudo crear el trabajo: $respuesta2"
else
  estado2="$(esperar_estado_final "$t2")"
  proveedor2="$(campo_trabajo "$t2" proveedor_id)"
  criterio CASO-2a "$([ "$estado2" = CANCELADO ] && [ -z "$proveedor2" ] && echo 0 || echo 1)" \
    "GET /trabajos/$t2 -> estado=$estado2, proveedor_id='$proveedor2' (esperado CANCELADO, sin proveedor_id)"

  estado_saga2="$(campo_saga "$t2" estado)"
  criterio CASO-2b "$([ "$estado_saga2" = COMPENSADA ] && echo 0 || echo 1)" \
    "GET /sagas/$t2 -> estado=$estado_saga2 (esperado COMPENSADA)"
  reversiones2="$(pasos_de "$t2" | grep -c '^REVERSION' || true)"
  criterio CASO-2c "$([ "${reversiones2:-0}" -ge 1 ] && echo 0 || echo 1)" \
    "GET /sagas/$t2 -> ${reversiones2:-0} paso(s) de reversión (esperado >= 1: candidatos-liberados y/o vigencia-rechazada)"
fi

# ------------------------------------------------------------- Caso 3 (CA-1.4)
resultado ""
resultado "## Caso 3 — simular_fallo=SIN_CANDIDATOS"

respuesta3="$(crear_trabajo SIN_CANDIDATOS)"
t3="$(echo "$respuesta3" | trabajo_id_de)"
if [ -z "$t3" ]; then
  criterio CASO-3a 1 "no se pudo crear el trabajo: $respuesta3"
else
  estado3="$(esperar_estado_final "$t3")"
  criterio CASO-3a "$([ "$estado3" = CANCELADO ] && echo 0 || echo 1)" \
    "GET /trabajos/$t3 -> estado=$estado3 (esperado CANCELADO directo)"

  estado_saga3="$(campo_saga "$t3" estado)"
  n_pasos3="$(pasos_de "$t3" | wc -l | tr -d ' ')"
  criterio CASO-3b "$([ "$estado_saga3" = COMPENSADA ] && echo 0 || echo 1)" \
    "GET /sagas/$t3 -> estado=$estado_saga3 (esperado COMPENSADA)"
  criterio CASO-3c "$([ "$n_pasos3" = 2 ] && echo 0 || echo 1)" \
    "GET /sagas/$t3 -> ${n_pasos3} paso(s) (esperados 2: creado, cancelado)"
fi

# ------------------------------------------------------------- Caso 4 (CA-1.5)
resultado ""
resultado "## Caso 4 — simular_fallo=ASIGNACION"

respuesta4="$(crear_trabajo ASIGNACION)"
t4="$(echo "$respuesta4" | trabajo_id_de)"
if [ -z "$t4" ]; then
  criterio CASO-4a 1 "no se pudo crear el trabajo: $respuesta4"
else
  estado4="$(esperar_estado_final "$t4")"
  criterio CASO-4a "$([ "$estado4" = CANCELADO ] && echo 0 || echo 1)" \
    "GET /trabajos/$t4 -> estado=$estado4 (esperado CANCELADO tras confirmar vigencia)"

  estado_saga4="$(campo_saga "$t4" estado)"
  criterio CASO-4b "$([ "$estado_saga4" = COMPENSADA ] && echo 0 || echo 1)" \
    "GET /sagas/$t4 -> estado=$estado_saga4 (esperado COMPENSADA)"
  liberado4="$(pasos_de "$t4" | grep -c 'candidatos-liberados' || true)"
  criterio CASO-4c "$([ "${liberado4:-0}" -ge 1 ] && echo 0 || echo 1)" \
    "GET /sagas/$t4 -> candidatos-liberados presente (esperado >= 1, proveedor liberado tras la falla de asignación)"
fi

# ------------------------------------------------------------------ SC-004
FIN_EPOCH=$(date +%s)
DURACION_S=$((FIN_EPOCH - INICIO_EPOCH))
resultado ""
resultado "## SC-004 — duración total"
criterio SC-004 "$([ "$DURACION_S" -lt 300 ] && echo 0 || echo 1)" \
  "los cuatro casos tardaron ${DURACION_S}s (esperado < 300s / 5 min)"

# ---------------------------------------------------------------- resumen
resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · los 4 casos de la saga completos · detalle en $SALIDA"
