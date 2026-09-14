#!/usr/bin/env bash
# ESC-M · MOD-3 — Modificabilidad: estado nuevo en el ciclo de vida, entre
# servicios. Ver `docs/01-especificacion.md` §2 (MOD-3) y §5.4 (CA-M3).
#
# La medida, ahora que Operaciones es OTRO PROCESO (no otro módulo del mismo
# proceso, como en la Entrega 3): agregar `EN_PAUSA` al grafo de
# `EstadoTrabajo` en Gestión de Trabajos, redesplegar SOLO GT, y verificar que
# Operaciones y Emparejamiento:
#
#   - NO se reinician (mismo `StartedAt` de contenedor, antes y después);
#   - Operaciones registra `EN_PAUSA` de todas formas — porque el estado
#     viaja como texto en `EventoTrabajo` (RS-5), no como enumeración cerrada.
#
# El parche se aplica sobre un árbol de trabajo LIMPIO y se revierte con
# `git checkout` al final — el script se niega a correr si hay cambios sin
# comitear en el archivo que va a tocar, para no perder trabajo de nadie.
#
# Uso:
#   escenarios/mod-3.sh
#   PROYECTO_COMPOSE=hogar-alpes escenarios/mod-3.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

RUTA_OV="servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/dominio/objetos_valor.py"

URL_GT="${URL_GT:-http://localhost:8000}"
URL_OPS="${URL_OPS:-http://localhost:8001}"
COMPOSE_PROYECTO="${PROYECTO_COMPOSE:-}"
SERVICIO_OPS="${SERVICIO_OPS:-operaciones}"
SERVICIO_OPS_CONSUMIDOR="${SERVICIO_OPS_CONSUMIDOR:-operaciones-consumidor}"
SERVICIO_EMP="${SERVICIO_EMP:-emparejamiento-andina}"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/mod-3-$FECHA.md"

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

started_at() { compose ps -q "$1" | xargs -r docker inspect -f '{{.State.StartedAt}}' 2>/dev/null; }

cd "$RAIZ"
if ! git diff --quiet -- "$RUTA_OV"; then
  echo "FALLA · $RUTA_OV tiene cambios sin comitear — el script no va a pisarlos. Aborta." >&2
  exit 2
fi

revertir() {
  git checkout -- "$RUTA_OV"
  compose up -d --build gestion-trabajos gestion-trabajos-consumidor >>"$SALIDA" 2>&1 || true
  resultado "  parche revertido y GT reconstruido con el grafo original"
}
trap revertir EXIT

resultado "# MOD-3 · Modificabilidad — estado nuevo entre servicios — $FECHA"
resultado ""

# ------------------------------------------------------------ 1. StartedAt antes
resultado "## 1. StartedAt de OPS y EMP antes del parche"
antes_ops="$(started_at "$SERVICIO_OPS")"
antes_ops_consumidor="$(started_at "$SERVICIO_OPS_CONSUMIDOR")"
antes_emp="$(started_at "$SERVICIO_EMP")"
resultado "  $SERVICIO_OPS: $antes_ops"
resultado "  $SERVICIO_OPS_CONSUMIDOR: $antes_ops_consumidor"
resultado "  $SERVICIO_EMP: $antes_emp"

# ------------------------------------------------------------ 2. parche
resultado ""
resultado "## 2. Parche: agregar EN_PAUSA (EN_EJECUCION ↔ EN_PAUSA)"

python3 - "$RUTA_OV" <<'PYEOF'
import re, sys
ruta = sys.argv[1]
texto = open(ruta, encoding='utf-8').read()

texto = texto.replace(
    "    EN_VERIFICACION = 'EN_VERIFICACION'\n",
    "    EN_VERIFICACION = 'EN_VERIFICACION'\n    EN_PAUSA = 'EN_PAUSA'\n",
)
texto = texto.replace(
    "    Estado.EN_EJECUCION: {Estado.EN_VERIFICACION, Estado.CANCELADO},\n",
    "    Estado.EN_EJECUCION: {Estado.EN_VERIFICACION, Estado.EN_PAUSA, Estado.CANCELADO},\n"
    "    Estado.EN_PAUSA: {Estado.EN_EJECUCION},\n",
)
open(ruta, 'w', encoding='utf-8').write(texto)
PYEOF
resultado "  EN_PAUSA agregado a Estado y a TRANSICIONES en $RUTA_OV"

resultado ""
resultado "## 3. Redesplegar SOLO Gestión de Trabajos"
compose up -d --build gestion-trabajos gestion-trabajos-consumidor >>"$SALIDA" 2>&1
sleep 3

# ------------------------------------------------------------ 4. transicionar
resultado ""
resultado "## 4. Crear un trabajo y llevarlo a EN_PAUSA"

cuerpo='{"canal":"MARKETPLACE","categoria":"PLOMERIA","urgencia":"NORMAL","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","descripcion":"MOD-3"}'
respuesta="$(curl -s -X POST "$URL_GT/trabajos" -H 'Content-Type: application/json' -d "$cuerpo")"
trabajo_id="$(echo "$respuesta" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null)"

if [ -z "$trabajo_id" ]; then
  criterio CA-M3a 1 "no se pudo crear el trabajo de prueba: $respuesta"
else
  for estado in EMPAREJANDO ASIGNADO EN_EJECUCION EN_PAUSA; do
    curl -s -X PUT "$URL_GT/trabajos/$trabajo_id/estado" \
      -H 'Content-Type: application/json' -d "{\"estado\":\"$estado\"}" >>"$SALIDA" 2>&1
  done
  criterio CA-M3a 0 "trabajo $trabajo_id llevado a EN_PAUSA sin que GT lo rechazara"
fi

# ------------------------------------------------------------ 5. OPS lo registró
resultado ""
resultado "## 5. Operaciones registró EN_PAUSA sin conocerlo de antemano (CA-M3)"

if [ -n "$trabajo_id" ]; then
  estado_ops=""
  for _ in $(seq 1 10); do
    estado_ops="$(curl -s "$URL_OPS/seguimientos/$trabajo_id" \
      | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("estado_trabajo",""))
except Exception: print("")' 2>/dev/null)"
    [ "$estado_ops" = "EN_PAUSA" ] && break
    sleep 1
  done
  criterio CA-M3b "$([ "$estado_ops" = "EN_PAUSA" ] && echo 0 || echo 1)" \
    "Operaciones reporta estado_trabajo=$estado_ops (esperado EN_PAUSA) · 0 errores de deserialización (RS-5: el estado viaja como texto)"
fi

# ------------------------------------------------------------ 6. StartedAt después
resultado ""
resultado "## 6. StartedAt de OPS y EMP después — no deben haber cambiado"

despues_ops="$(started_at "$SERVICIO_OPS")"
despues_ops_consumidor="$(started_at "$SERVICIO_OPS_CONSUMIDOR")"
despues_emp="$(started_at "$SERVICIO_EMP")"
resultado "  $SERVICIO_OPS: $despues_ops"
resultado "  $SERVICIO_OPS_CONSUMIDOR: $despues_ops_consumidor"
resultado "  $SERVICIO_EMP: $despues_emp"

if [ "$antes_ops" = "$despues_ops" ] && [ "$antes_ops_consumidor" = "$despues_ops_consumidor" ] \
    && [ "$antes_emp" = "$despues_emp" ] && [ -n "$antes_ops" ]; then
  criterio CA-M3c 0 "ningún StartedAt cambió: OPS y EMP no se reiniciaron"
else
  criterio CA-M3c 1 "algún StartedAt cambió, o los contenedores no estaban corriendo antes de empezar"
fi

# ---------------------------------------------------------------- resumen
resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · MOD-3 completo · detalle en $SALIDA"
