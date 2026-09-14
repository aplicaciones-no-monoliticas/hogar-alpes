#!/usr/bin/env bash
# ESC-M · MOD-2 — Modificabilidad: país nuevo sin redesplegar el servicio base.
# Ver `docs/01-especificacion.md` §2 (MOD-2) y §5.4 (CA-M2).
#
# La medida: 0 cambios en el código del servicio. Se agrega una entrada a
# `infra/sidecar/reglas_regionales.json` (el volumen que lee el sidecar, ver
# `infra/sidecar/README.md`) y se reinicia el proceso — no se reconstruye la
# imagen. Se usa **Chile (CL)**, no Perú: la colección de Postman ya tiene un
# caso que depende de que Perú NO esté configurado (cae al contrato
# `_default`); agregar Perú aquí invalidaría esa prueba en vez de sumarse a
# ella.
#
# Verificación en dos partes:
#   a. CL acepta su categoría configurada y rechaza una que no lo está —
#      curl directo, porque Postman no conoce a CL.
#   b. La carpeta "Escenario 2" de Postman sigue en verde: agregar un país no
#      rompió los que ya estaban (incluido el caso de Perú).
#
# El archivo del sidecar se revierte al final: la corrida es idempotente.
#
# Uso:
#   escenarios/mod-2.sh
#   PROYECTO_COMPOSE=hogar-alpes escenarios/mod-2.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

SIDECAR="$RAIZ/infra/sidecar/reglas_regionales.json"
RESPALDO="$SIDECAR.antes-de-mod-2"

URL_GT="${URL_GT:-http://localhost:8000}"
COMPOSE_PROYECTO="${PROYECTO_COMPOSE:-}"
COLECCION="$RAIZ/postman/hogar-alpes.postman_collection.json"
ENTORNO="${ENTORNO:-$RAIZ/postman/hogar-alpes.postman_environment.json}"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/mod-2-$FECHA.md"

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

revertir() {
  if [ -f "$RESPALDO" ]; then
    mv "$RESPALDO" "$SIDECAR"
    compose restart gestion-trabajos gestion-trabajos-consumidor >>"$SALIDA" 2>&1 || true
    resultado "  sidecar revertido a su contenido original"
  fi
}
trap revertir EXIT

resultado "# MOD-2 · Modificabilidad — país nuevo por sidecar — $FECHA"
resultado ""

# ---------------------------------------------------------------- 1. agregar CL
resultado "## 1. Agregar Chile (CL) al sidecar, sin tocar código"

cp "$SIDECAR" "$RESPALDO"
python3 - "$SIDECAR" <<'PYEOF'
import json, sys
ruta = sys.argv[1]
with open(ruta, encoding='utf-8') as f:
    reglas = json.load(f)
reglas['CL'] = {
    'categorias': ['PLOMERIA', 'ELECTRICIDAD', 'GAS'],
    'urgencias': ['CRITICA', 'ALTA', 'NORMAL'],
}
with open(ruta, 'w', encoding='utf-8') as f:
    json.dump(reglas, f, ensure_ascii=False, indent=2)
PYEOF
resultado "  CL agregado a $SIDECAR (categorías: PLOMERIA, ELECTRICIDAD, GAS)"

resultado ""
resultado "## 2. Reiniciar el sidecar (el proceso, no la imagen)"
compose restart gestion-trabajos gestion-trabajos-consumidor >>"$SALIDA" 2>&1
sleep 3

# ------------------------------------------------------------- 3. verificar CL
resultado ""
resultado "## 3. CL aplica sus propias reglas (CA-M2)"

cuerpo_permitido='{"canal":"MARKETPLACE","categoria":"GAS","urgencia":"ALTA","pais":"CL","ciudad":"Santiago","direccion":"Providencia 123","descripcion":"Fuga de gas"}'
codigo_permitido=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL_GT/trabajos" \
  -H 'Content-Type: application/json' -d "$cuerpo_permitido")
criterio CA-M2a "$([ "$codigo_permitido" = "202" ] && echo 0 || echo 1)" \
  "GAS en Chile → $codigo_permitido (esperado 202)"

cuerpo_no_permitido='{"canal":"MARKETPLACE","categoria":"SISMO","urgencia":"ALTA","pais":"CL","ciudad":"Santiago","direccion":"Providencia 123","descripcion":"SISMO no está en la lista de CL"}'
codigo_no_permitido=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL_GT/trabajos" \
  -H 'Content-Type: application/json' -d "$cuerpo_no_permitido")
criterio CA-M2b "$([ "$codigo_no_permitido" = "400" ] && echo 0 || echo 1)" \
  "SISMO en Chile (no configurado para CL) → $codigo_no_permitido (esperado 400)"

# --------------------------------------------------- 4. escenario 2 sigue verde
resultado ""
resultado "## 4. La carpeta \"Escenario 2\" de Postman sigue en verde"

if command -v newman >/dev/null 2>&1; then
  NEWMAN="newman"
elif command -v npx >/dev/null 2>&1; then
  NEWMAN="npx --yes newman"
else
  NEWMAN=""
fi

if [ -z "$NEWMAN" ]; then
  criterio CA-M2c 1 "newman no está disponible — correr manualmente: newman run $COLECCION -e $ENTORNO --folder 'Escenario 2 · Modificabilidad — reglas regionales por sidecar'"
else
  if $NEWMAN run "$COLECCION" -e "$ENTORNO" \
      --folder "Escenario 2 · Modificabilidad — reglas regionales por sidecar" \
      >>"$SALIDA" 2>&1; then
    criterio CA-M2c 0 "0 archivos de código cambiados y la carpeta del escenario 2 (incluido Perú) sigue en verde"
  else
    criterio CA-M2c 1 "newman reportó fallos — ver detalle en $SALIDA"
  fi
fi

# ---------------------------------------------------------------- resumen
resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · MOD-2 completo · detalle en $SALIDA"
