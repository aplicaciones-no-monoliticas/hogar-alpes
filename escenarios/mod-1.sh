#!/usr/bin/env bash
# ESC-M · MOD-1 — Modificabilidad: reemplazar el adaptador de persistencia.
# Ver `docs/01-especificacion.md` §2 (MOD-1) y §5.4 (CA-M1).
#
# La medida: 0 cambios en `dominio/` ni `aplicacion/` al agregar o elegir un
# segundo adaptador de `RepositorioTrabajos`. Dos verificaciones:
#
#   1. Estática — el commit que agregó `repositorios_memoria.py` no toca esas
#      dos carpetas (`git diff --stat`).
#   2. Dinámica — con GT reiniciado en `ADAPTADOR_TRABAJOS=memoria`, las
#      carpetas de Postman de los escenarios 2 y 3 siguen en verde.
#
# Uso:
#   escenarios/mod-1.sh
#   COMMIT_ADAPTADOR=<sha> escenarios/mod-1.sh   # si el commit por defecto no aplica
#   PROYECTO_COMPOSE=hogar-alpes escenarios/mod-1.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

RUTA_MEMORIA="servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/infraestructura/repositorios_memoria.py"
RUTA_DOMINIO="servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/dominio"
RUTA_APLICACION="servicios/gestion_trabajos/src/gestion_trabajos/modulos/trabajos/aplicacion"

URL_GT="${URL_GT:-http://localhost:8000}"
COMPOSE_PROYECTO="${PROYECTO_COMPOSE:-}"
COLECCION="$RAIZ/postman/hogar-alpes.postman_collection.json"
ENTORNO="${ENTORNO:-$RAIZ/postman/hogar-alpes.postman_environment.json}"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/mod-1-$FECHA.md"

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

resultado "# MOD-1 · Modificabilidad — reemplazar el adaptador de persistencia — $FECHA"
resultado ""

# ---------------------------------------------------------------- 1. estática
resultado "## 1. El commit que agregó el adaptador no toca dominio/ ni aplicacion/"

cd "$RAIZ"
COMMIT_ADAPTADOR="${COMMIT_ADAPTADOR:-$(git log --format='%H' -1 -- "$RUTA_MEMORIA")}"
if [ -z "$COMMIT_ADAPTADOR" ]; then
  criterio CA-M1a 1 "no se encontró un commit que agregue $RUTA_MEMORIA — ¿ya está fusionado?"
else
  DIFF_SENSIBLE="$(git diff --stat "${COMMIT_ADAPTADOR}^" "$COMMIT_ADAPTADOR" -- "$RUTA_DOMINIO" "$RUTA_APLICACION" 2>/dev/null)"
  resultado "  commit: $COMMIT_ADAPTADOR"
  if [ -z "$DIFF_SENSIBLE" ]; then
    criterio CA-M1a 0 "git diff --stat de dominio/ y aplicacion/ está vacío para ese commit"
  else
    resultado '```'
    resultado "$DIFF_SENSIBLE"
    resultado '```'
    criterio CA-M1a 1 "el commit SÍ tocó dominio/ o aplicacion/ — ver arriba"
  fi
fi

# --------------------------------------------------------------- 2. dinámica
resultado ""
resultado "## 2. GT con ADAPTADOR_TRABAJOS=memoria, Postman de los escenarios 2 y 3"

resultado "  reiniciando gestion-trabajos con el adaptador en memoria (WORKERS=1: el"
resultado "  adaptador es por proceso, ver docker-compose.yml)…"
ADAPTADOR_TRABAJOS=memoria WORKERS=1 compose up -d gestion-trabajos gestion-trabajos-consumidor \
  >>"$SALIDA" 2>&1
sleep 3

salud="$(curl -s -o /dev/null -w '%{http_code}' "$URL_GT/health" 2>/dev/null || echo 000)"
if [ "$salud" != "200" ]; then
  criterio CA-M1b 1 "GT no respondió /health tras el reinicio (código $salud)"
else
  if command -v newman >/dev/null 2>&1; then
    NEWMAN="newman"
  elif command -v npx >/dev/null 2>&1; then
    NEWMAN="npx --yes newman"
  else
    NEWMAN=""
  fi

  if [ -z "$NEWMAN" ]; then
    criterio CA-M1b 1 "newman no está disponible en este entorno — correr manualmente: newman run $COLECCION -e $ENTORNO --folder 'Escenario 2 · Modificabilidad — reglas regionales por sidecar' --folder 'Escenario 3 · Modificabilidad — ciclo de vida del Trabajo'"
  else
    if $NEWMAN run "$COLECCION" -e "$ENTORNO" \
        --folder "Escenario 2 · Modificabilidad — reglas regionales por sidecar" \
        --folder "Escenario 3 · Modificabilidad — ciclo de vida del Trabajo" \
        >>"$SALIDA" 2>&1; then
      criterio CA-M1b 0 "las carpetas de Postman de los escenarios 2 y 3 pasaron con el adaptador en memoria"
    else
      criterio CA-M1b 1 "newman reportó fallos — ver detalle en $SALIDA"
    fi
  fi
fi

# --------------------------------------------------------------- revertir
resultado ""
resultado "## 3. Revertir al adaptador de producción"
compose up -d gestion-trabajos gestion-trabajos-consumidor >>"$SALIDA" 2>&1
resultado "  gestion-trabajos reiniciado con ADAPTADOR_TRABAJOS=postgres (valor por defecto)"

# ---------------------------------------------------------------- resumen
resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"
  exit 1
fi
resultado "PASA · MOD-1 completo · detalle en $SALIDA"
