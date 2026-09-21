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
# `comun.sh` trae la topología, el cliente de administración y —lo importante—
# `crear_region`, que es la ÚNICA definición de qué tópicos y suscripciones
# lleva una región. Así el alta en caliente no puede desviarse de esto.
# shellcheck source=comun.sh
source "$DIR/comun.sh"

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
  # Misma definición que usa `agregar-region.sh`: una región creada en caliente
  # es indistinguible de una creada aquí.
  crear_region "$region"
  # Saga (Entrega 5, T045/D6): `saga-log` cubre todas las regiones con un
  # patrón (`evt-trabajo-.*`), como ya hace GT con `cmd-trabajo-.*`. Se
  # pre-crea aquí, fuera de `crear_region`, para no acoplar un servicio nuevo
  # a la única definición que usa también el alta en caliente (D6 explícito:
  # no hace falta tocar `crear_region`; una región agregada en caliente
  # después de esta entrega queda sin esta suscripción puntual).
  crear_suscripcion "persistent://$TENANT/$NS_TRABAJOS/evt-trabajo-$region" "saga-log"
done

echo
echo "acreditación"
cmd_acr="persistent://$TENANT/$NS_ACREDITACION/cmd-acreditacion"
evt_acr="persistent://$TENANT/$NS_ACREDITACION/evt-acreditacion"
crear_topico "$cmd_acr"
crear_topico "$evt_acr"
crear_suscripcion "$cmd_acr" "acreditacion"
crear_suscripcion "$evt_acr" "emparejamiento-proyeccion"
# Saga (Entrega 5, D6 de specs/002-saga-asignacion-trabajo/research.md): GT
# escucha vigencia-confirmada/rechazada, Emparejamiento escucha vigencia-rechazada
# para liberar su reserva.
crear_suscripcion "$evt_acr" "gestion-trabajos-saga"
crear_suscripcion "$evt_acr" "emparejamiento-saga"
crear_suscripcion "$evt_acr" "saga-log"

echo
echo "emparejamiento"
evt_emp="persistent://$TENANT/$NS_EMPAREJAMIENTO/evt-emparejamiento"
crear_topico "$evt_emp"
# Saga (Entrega 5, D6): Acreditación escucha proveedor-propuesto para confirmar
# vigencia; GT escucha sin-candidatos para compensar.
crear_suscripcion "$evt_emp" "acreditacion"
crear_suscripcion "$evt_emp" "gestion-trabajos-saga"
crear_suscripcion "$evt_emp" "saga-log"

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

resumen "topología creada"
