#!/usr/bin/env bash
# INF-3 · Crea la topología de mensajería. Idempotente: se puede correr las
# veces que haga falta.
#
# Crea el tenant, los tres namespaces con sus políticas, los tópicos
# particionados de las regiones iniciales y —esto es lo importante— las
# suscripciones POR ADELANTADO.
#
# Por qué las suscripciones se crean aquí y no al arrancar cada servicio: en
# Pulsar, un mensaje publicado en un tópico sin suscripciones no se retiene para
# nadie. Si Operaciones nunca hubiera arrancado, sus eventos no existirían
# cuando por fin lo hiciera. Con la suscripción pre-creada, el backlog se
# acumula desde el primer mensaje, que es exactamente lo que el escenario 6
# necesita poder afirmar.
#
#   docker compose run --rm pulsar-config
#   PULSAR_ADMIN_URL=http://localhost:8080 bash infra/pulsar/inicializar.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=topologia.env
source "$DIR/topologia.env"

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

crear_namespace() {
  local ns="$TENANT/$1"
  echo
  echo "namespace $ns"
  aplicar "crear"                        $ADMIN namespaces create "$ns"
  aplicar "TTL ${TTL_SEGUNDOS}s (ventana del escenario 6)" \
          $ADMIN namespaces set-message-ttl "$ns" --messageTTL "$TTL_SEGUNDOS"
  # La retención va PRIMERO: Pulsar rechaza con HTTP 412 una cuota de backlog
  # mayor que la retención del namespace.
  aplicar "retención de confirmados $RETENCION_TAMANO / $RETENCION_TIEMPO" \
          $ADMIN namespaces set-retention "$ns" --size "$RETENCION_TAMANO" --time "$RETENCION_TIEMPO"
  aplicar "cuota de backlog $CUOTA_BACKLOG · $POLITICA_BACKLOG (nunca retiene al productor)" \
          $ADMIN namespaces set-backlog-quota "$ns" --limit "$CUOTA_BACKLOG" --policy "$POLITICA_BACKLOG"
  aplicar "compatibilidad de esquemas $COMPATIBILIDAD" \
          $ADMIN namespaces set-schema-compatibility-strategy "$ns" --compatibility "$COMPATIBILIDAD"
  aplicar "validación de esquema obligatoria" \
          $ADMIN namespaces set-schema-validation-enforce "$ns" --enable
  aplicar "creación automática de tópicos deshabilitada" \
          $ADMIN namespaces set-auto-topic-creation "$ns" --disable
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

echo "=== Topología de mensajería · $ADMIN_URL"

echo
echo "tenant $TENANT"
aplicar "crear (cluster $CLUSTER)" $ADMIN tenants create "$TENANT" --allowed-clusters "$CLUSTER"

crear_namespace "$NS_TRABAJOS"
crear_namespace "$NS_ACREDITACION"
crear_namespace "$NS_EMPAREJAMIENTO"

for region in $REGIONES_INICIALES; do
  echo
  echo "región $region"
  cmd="persistent://$TENANT/$NS_TRABAJOS/cmd-trabajo-$region"
  evt="persistent://$TENANT/$NS_TRABAJOS/evt-trabajo-$region"
  crear_topico "$cmd"
  crear_topico "$evt"
  crear_suscripcion "$cmd" "gestion-trabajos"
  crear_suscripcion "$evt" "operaciones"
  crear_suscripcion "$evt" "emparejamiento-$region"
done

echo
echo "acreditación"
cmd_acr="persistent://$TENANT/$NS_ACREDITACION/cmd-acreditacion"
evt_acr="persistent://$TENANT/$NS_ACREDITACION/evt-acreditacion"
crear_topico "$cmd_acr"
crear_topico "$evt_acr"
crear_suscripcion "$cmd_acr" "acreditacion"
crear_suscripcion "$evt_acr" "emparejamiento-proyeccion"

echo
echo "emparejamiento"
# Nadie lo consume en la Entrega 4: lo escuchará la saga de la Entrega 5. Por eso
# se crea el tópico pero no una suscripción que nadie atendería.
crear_topico "persistent://$TENANT/$NS_EMPAREJAMIENTO/evt-emparejamiento"

# La cuota de backlog es la política de la que depende el escenario 6, y su
# comando puede fallar por el acoplamiento con la retención. No basta con que
# nadie haya protestado: se relee del broker.
echo
echo "verificación · la cuota de backlog quedó aplicada"
for ns in "$NS_TRABAJOS" "$NS_ACREDITACION" "$NS_EMPAREJAMIENTO"; do
  cuota=$($ADMIN namespaces get-backlog-quotas "$TENANT/$ns" 2>/dev/null | tr -d '\n ')
  if grep -q "$POLITICA_BACKLOG" <<<"$cuota"; then
    echo "  ok      $TENANT/$ns · $POLITICA_BACKLOG"
  else
    echo "  FALLA   $TENANT/$ns · sin cuota explícita: manda el valor por defecto del broker"
    fallos=$((fallos + 1))
  fi
done

echo
echo "=============================================================="
if [ "$fallos" -gt 0 ]; then
  echo "FALLA · $fallos operaciones no se pudieron aplicar"
  exit 1
fi
echo "PASA · topología creada"
