#!/usr/bin/env bash
# INF-4 · Agrega una región en caliente, con el sistema en operación.
#
# Es el paso que mide CA-8.4 del escenario 8: *«las regiones existentes
# continúan operando sin interrupción durante la incorporación de capacidad»*.
# Agregar una región es crear su stream y su grupo de consumidores; **ningún
# tópico existente se toca, ningún servicio se reinicia**.
#
# Los consumidores de Operaciones la descubren solos, porque se suscriben por
# patrón (`evt-trabajo-.*`). Emparejamiento necesita levantar su réplica de la
# región, que es una unidad de despliegue nueva, no un cambio en las existentes.
#
#   docker compose run --rm pulsar-config bash /infra/agregar-region.sh conosur
#   PULSAR_ADMIN_URL=http://localhost:8080 bash infra/pulsar/agregar-region.sh conosur

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=comun.sh
source "$DIR/comun.sh"

REGION="${1:-}"

if [ -z "$REGION" ]; then
  echo "Uso: agregar-region.sh <región>"
  echo
  echo "Regiones ya creadas por la inicialización: $REGIONES_INICIALES"
  echo "Ejemplo: agregar-region.sh conosur"
  exit 2
fi

if ! [[ "$REGION" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "FALLA · nombre de región inválido: '$REGION'"
  echo "        Solo minúsculas, dígitos y guiones. El nombre va en el tópico."
  exit 2
fi

echo "=== Alta de región '$REGION' · $ADMIN_URL"
echo
echo "creación"
crear_region "$REGION"

echo
echo "verificación contra el broker"
verificar_region "$REGION"

resumen "región '$REGION' disponible · los tópicos de las otras regiones no se tocaron"
