#!/usr/bin/env bash
# Funciones compartidas por `inicializar.sh` y `agregar-region.sh`.
#
# La razón de que exista este archivo: **la forma de una región se define una
# sola vez**. Si agregar una región en caliente creara tópicos o suscripciones
# distintas de las que crea la inicialización, la región nueva quedaría sutilmente
# rota y el escenario 8 mediría otra cosa. `crear_region` es la única definición.

DIR_COMUN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=topologia.env
source "$DIR_COMUN/topologia.env"

ADMIN_URL="${PULSAR_ADMIN_URL:-http://broker-1:8080}"
ADMIN="${PULSAR_BIN:-/pulsar/bin}/pulsar-admin --admin-url $ADMIN_URL"

fallos=0

# Ejecuta una orden de administración tolerando que el objeto ya exista.
# Cualquier otro error se reporta y hace fallar el script.
aplicar() {
  local descripcion="$1"; shift
  local salida
  if salida=$("$@" 2>&1); then
    echo "  ok      $descripcion"
  elif grep -qiE "already exists|Conflict|409" <<<"$salida"; then
    echo "  existe  $descripcion"
  else
    echo "  FALLA   $descripcion"
    echo "          ${salida//$'\n'/$'\n'          }" | head -6
    fallos=$((fallos + 1))
  fi
}

crear_topico() {
  local topico="$1"
  aplicar "tópico $topico ($PARTICIONES particiones)" \
          $ADMIN topics create-partitioned-topic "$topico" --partitions "$PARTICIONES"
}

crear_suscripcion() {
  local topico="$1" suscripcion="$2"
  aplicar "suscripción $suscripcion en $(basename "$topico")" \
          $ADMIN topics create-subscription "$topico" --subscription "$suscripcion" --messageId earliest
}

# Una región = dos tópicos particionados y tres suscripciones.
# Es la única definición: la usan tanto la inicialización como el alta en caliente.
crear_region() {
  local region="$1"
  local cmd="persistent://$TENANT/$NS_TRABAJOS/cmd-trabajo-$region"
  local evt="persistent://$TENANT/$NS_TRABAJOS/evt-trabajo-$region"

  crear_topico "$cmd"
  crear_topico "$evt"
  crear_suscripcion "$cmd" "gestion-trabajos"
  crear_suscripcion "$evt" "operaciones"
  crear_suscripcion "$evt" "emparejamiento-$region"
}

# Comprueba contra el broker que la región quedó como debe: no basta con que
# ningún comando haya protestado (lección de INF-3).
verificar_region() {
  local region="$1"
  local evt="persistent://$TENANT/$NS_TRABAJOS/evt-trabajo-$region"
  local subs particiones

  particiones=$($ADMIN topics get-partitioned-topic-metadata "$evt" 2>/dev/null | grep -o '"partitions"[^,]*' | grep -o '[0-9]\+')
  if [ "${particiones:-0}" = "$PARTICIONES" ]; then
    echo "  ok      evt-trabajo-$region tiene $PARTICIONES particiones"
  else
    echo "  FALLA   evt-trabajo-$region: particiones=${particiones:-ninguna}, se esperaban $PARTICIONES"
    fallos=$((fallos + 1))
  fi

  subs=$($ADMIN topics subscriptions "$evt" 2>/dev/null | tr -d ' ')
  for esperada in "operaciones" "emparejamiento-$region"; do
    if grep -qx "$esperada" <<<"$subs"; then
      echo "  ok      suscripción $esperada existe y espera mensajes"
    else
      echo "  FALLA   falta la suscripción $esperada en evt-trabajo-$region"
      fallos=$((fallos + 1))
    fi
  done
}

resumen() {
  echo
  echo "=============================================================="
  if [ "$fallos" -gt 0 ]; then
    echo "FALLA · $fallos operaciones no se pudieron aplicar"
    exit 1
  fi
  echo "PASA · $1"
}
