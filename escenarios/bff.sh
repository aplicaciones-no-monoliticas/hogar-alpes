#!/usr/bin/env bash
# US-02 · BFF — un solo punto de entrada y trazabilidad por petición.
# Ver specs/001-bff-entry-point/spec.md, contracts/ y quickstart.md.
#
# Verifica contra el sistema levantado (`docker compose up -d --build`) lo que
# las pruebas unitarias no pueden: un servicio detenido de verdad, los registros
# de los contenedores y los mensajes reales del broker. Cada criterio termina en
# PASA, FALLA o PENDIENTE. PENDIENTE = no se pudo ejecutar (nunca cuenta como
# PASA); lo que depende de US-01 (`saga-log`) se reporta así.
#
# Uso:
#   escenarios/bff.sh
#   SECCIONES="us1" escenarios/bff.sh          # solo una sección
#   URL_BFF=http://localhost:8090 PROYECTO_COMPOSE=hogar-alpes escenarios/bff.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"

URL_BFF="${URL_BFF:-http://localhost:8090}"
COMPOSE_PROYECTO="${PROYECTO_COMPOSE:-}"
PYTHON="${PYTHON:-python3}"
SECCIONES="${SECCIONES:-us1 us2 us3}"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/bff-$FECHA.md"
TMP="$(mktemp -d)"

CUERPO_TRABAJO='{"categoria":"PLOMERIA","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","urgencia":"NORMAL"}'
RUTA_CANDIDATOS='/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota'

fallos=0
pendientes=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then
    resultado "  PASA       $id · $detalle"
  else
    resultado "  FALLA      $id · $detalle"
    fallos=$((fallos + 1))
  fi
}
pendiente() {
  resultado "  PENDIENTE  $1 · $2"
  pendientes=$((pendientes + 1))
}

COMPOSE=(docker compose)
[ -n "$COMPOSE_PROYECTO" ] && COMPOSE=(docker compose -p "$COMPOSE_PROYECTO")
compose() { "${COMPOSE[@]}" "$@"; }

# http METODO RUTA [CUERPO] [opciones de curl…]
# Deja en CODIGO, CABECERAS y CUERPO la última respuesta (000 si no hubo).
http() {
  local metodo="$1" ruta="$2" cuerpo="${3:-}"
  shift 2
  [ $# -gt 0 ] && shift
  local args=(-s -X "$metodo" -D "$TMP/cabeceras" -o "$TMP/cuerpo" -w '%{http_code}' "$@")
  [ -n "$cuerpo" ] && args+=(-H 'Content-Type: application/json' --data "$cuerpo")
  CODIGO="$(curl "${args[@]}" "$URL_BFF$ruta" 2>/dev/null || true)"
  CODIGO="${CODIGO:-000}"
  CABECERAS="$(tr -d '\r' <"$TMP/cabeceras" 2>/dev/null || true)"
  CUERPO="$(cat "$TMP/cuerpo" 2>/dev/null || true)"
}

# cabecera NOMBRE → valor de esa cabecera en la última respuesta
cabecera() { printf '%s\n' "$CABECERAS" | grep -i "^$1:" | head -1 | sed 's/^[^:]*: *//'; }

# campo a.b.c → valor de esa ruta en el JSON de la última respuesta (vacío si no existe)
campo() {
  printf '%s' "$CUERPO" | "$PYTHON" -c '
import json, sys
try:
    d = json.load(sys.stdin)
    for k in sys.argv[1].split("."):
        d = d[k]
    print(json.dumps(d) if isinstance(d, (dict, list)) else d)
except Exception:
    pass
' "$1"
}

# esperar_bff RUTA CODIGO SEGUNDOS → 0 si el BFF responde ese código antes del tope
esperar_bff() {
  local ruta="$1" esperado="$2" tope="$3" i
  for ((i = 0; i < tope; i++)); do
    http GET "$ruta"
    [ "$CODIGO" = "$esperado" ] && return 0
    sleep 1
  done
  return 1
}

# claves a.b → claves del objeto JSON en esa ruta, ordenadas y separadas por coma
claves() {
  printf '%s' "$CUERPO" | "$PYTHON" -c '
import json, sys
try:
    d = json.load(sys.stdin)
    for k in sys.argv[1].split("."):
        d = d[k]
    print(",".join(sorted(d)))
except Exception:
    pass
' "$1"
}

uuid_nuevo() { "$PYTHON" -c 'import uuid; print(uuid.uuid4())'; }

# Operaciones se detiene en varias secciones; se vuelve a levantar siempre, pase lo que pase.
OPERACIONES_DETENIDAS=0
detener_operaciones() {
  OPERACIONES_DETENIDAS=1
  compose stop operaciones operaciones-consumidor >>"$SALIDA" 2>&1
}
restaurar_operaciones() {
  [ "$OPERACIONES_DETENIDAS" = 1 ] || return 0
  compose start operaciones operaciones-consumidor >>"$SALIDA" 2>&1
  OPERACIONES_DETENIDAS=0
  if esperar_bff "/seguimientos/conteo" 200 60; then
    resultado "  Operaciones respondió otra vez a través del BFF"
  else
    resultado "  ADVERTENCIA · Operaciones no volvió a responder en 60 s; las secciones siguientes pueden fallar"
  fi
}

limpiar() { rm -rf "$TMP"; }
SUSCRIPCIONES_CREADAS=0
salir() {
  restaurar_operaciones
  [ "$SUSCRIPCIONES_CREADAS" = 1 ] && borrar_suscripciones_temporales
  limpiar
}
trap salir EXIT

resultado "# US-02 · BFF — verificación contra el sistema levantado — $FECHA"
resultado ""

http GET /health
if [ "$CODIGO" != "200" ]; then
  pendiente "BFF" "no responde /health en $URL_BFF (código $CODIGO): levantar con 'docker compose up -d --build' y repetir"
  resultado ""
  resultado "## Resumen"
  resultado "PENDIENTE · nada se pudo verificar · detalle en $SALIDA"
  exit 2
fi

# ------------------------------------------------------------------ US1
seccion_us1() {
  resultado "## US1 · Una sola dirección y un servicio caído (CA-2.14, CA-2.15, CA-2.17)"

  if ! command -v docker >/dev/null 2>&1; then
    pendiente "CA-2.14" "docker no está disponible: no se puede detener un servicio"
    return
  fi

  http POST /trabajos "$CUERPO_TRABAJO"
  local id
  id="$(campo id)"
  if [ "$CODIGO" = "202" ] && [ -n "$id" ]; then
    criterio CA-2.5 0 "POST /trabajos por el BFF → 202 con id $id"
  else
    criterio CA-2.5 1 "POST /trabajos por el BFF → $CODIGO (se esperaba 202 con id): $CUERPO"
    return
  fi

  resultado "  deteniendo operaciones y operaciones-consumidor…"
  detener_operaciones

  http GET "/seguimientos/$id"
  local cuerpo_503="$CUERPO" cid_503
  cid_503="$(cabecera X-Correlation-Id)"
  if [ "$CODIGO" = "503" ] && [ "$(campo servicio)" = "operaciones" ]; then
    criterio CA-2.14a 0 "con Operaciones detenido, GET /seguimientos/$id → 503 que nombra 'operaciones'"
  else
    criterio CA-2.14a 1 "se esperaba 503 con servicio=operaciones; llegó $CODIGO: $cuerpo_503"
  fi
  if [ -n "$cid_503" ]; then
    criterio CA-2.17 0 "el 503 trae la cabecera X-Correlation-Id ($cid_503)"
  else
    criterio CA-2.17 1 "el 503 no trae la cabecera X-Correlation-Id"
  fi

  http GET "/trabajos/$id"
  local trabajo_codigo="$CODIGO" trabajo_cuerpo="$CUERPO"
  http GET "$RUTA_CANDIDATOS"
  if [ "$trabajo_codigo" = "200" ] && [ "$CODIGO" = "200" ]; then
    criterio CA-2.14b 0 "con Operaciones detenido, GET /trabajos/$id y GET /candidatos siguen en 200"
  else
    criterio CA-2.14b 1 "las demás rutas debían seguir en 200: trabajos=$trabajo_codigo candidatos=$CODIGO"
  fi

  if printf '%s\n%s\n%s' "$cuerpo_503" "$trabajo_cuerpo" "$CUERPO" | grep -q 'Traceback'; then
    criterio CA-2.15 1 "alguna respuesta trae una traza de error"
  else
    criterio CA-2.15 0 "ninguna respuesta trae una traza de error"
  fi

  resultado "  levantando operaciones y operaciones-consumidor de nuevo…"
  restaurar_operaciones
}

# ------------------------------------------------------------------ US2
seccion_us2() {
  resultado "## US2 · Consultas compuestas (CA-2.8, CA-2.9, CA-2.10, CA-2.11)"

  if ! command -v docker >/dev/null 2>&1; then
    pendiente "CA-2.9" "docker no está disponible: no se puede detener un servicio"
    return
  fi

  http POST /trabajos "$CUERPO_TRABAJO"
  local id
  id="$(campo id)"
  if [ "$CODIGO" != "202" ] || [ -z "$id" ]; then
    criterio CA-2.8 1 "no se pudo crear el trabajo de la prueba: $CODIGO $CUERPO"
    return
  fi

  # Consistencia eventual: el seguimiento llega por un evento, no por la creación.
  local i seguimiento=""
  for ((i = 0; i < 20; i++)); do
    http GET "/trabajos/$id/completo"
    seguimiento="$(campo partes.seguimiento.estado)"
    [ "$seguimiento" = "DISPONIBLE" ] && break
    sleep 1
  done
  if [ "$CODIGO" = "200" ] && [ "$(campo partes.trabajo.estado)" = "DISPONIBLE" ] && [ "$seguimiento" = "DISPONIBLE" ]; then
    criterio CA-2.8 0 "GET /trabajos/$id/completo → 200 con trabajo y seguimiento DISPONIBLE en una sola respuesta"
  else
    criterio CA-2.8 1 "se esperaba 200 con trabajo y seguimiento DISPONIBLE; llegó $CODIGO: $CUERPO"
  fi
  local emparejamiento
  emparejamiento="$(campo partes.emparejamiento.estado)"
  if [ "$emparejamiento" = "DISPONIBLE" ] || [ "$emparejamiento" = "TODAVIA_NO_DISPONIBLE" ]; then
    criterio CA-2.8 0 "la parte emparejamiento responde $emparejamiento (no falla)"
  else
    criterio CA-2.8 1 "la parte emparejamiento quedó $emparejamiento"
  fi
  local saga
  saga="$(campo partes.saga.estado)"
  if [ "$saga" = "DISPONIBLE" ]; then
    criterio CA-2.8 0 "la parte saga está DISPONIBLE"
  else
    pendiente "CA-2.8 (parte saga)" "la parte saga está '$saga': saga-log (US-01) todavía no existe"
  fi

  resultado "  deteniendo operaciones y operaciones-consumidor…"
  detener_operaciones
  http GET "/trabajos/$id/completo"
  if [ "$CODIGO" = "200" ] && [ "$(campo partes.seguimiento.estado)" = "NO_DISPONIBLE" ] && [ "$(campo partes.trabajo.estado)" = "DISPONIBLE" ]; then
    criterio CA-2.9 0 "con Operaciones detenido: 200, seguimiento NO_DISPONIBLE y trabajo DISPONIBLE"
  else
    criterio CA-2.9 1 "se esperaba 200 con seguimiento NO_DISPONIBLE; llegó $CODIGO: $CUERPO"
  fi
  restaurar_operaciones

  http GET /estado-del-sistema
  if [ "$CODIGO" = "200" ] && [ "$(claves componentes)" = "acreditacion,bff,emparejamiento,gestion-trabajos,operaciones,saga-log" ]; then
    criterio CA-2.10 0 "GET /estado-del-sistema → 200 con los seis componentes"
  else
    criterio CA-2.10 1 "se esperaba 200 con seis componentes; llegó $CODIGO: $CUERPO"
  fi
  if [ "$(campo componentes.saga-log.estado)" = "UP" ]; then
    [ "$(campo estado_general)" = "OK" ] && criterio CA-2.10 0 "estado_general OK" || criterio CA-2.10 1 "estado_general $(campo estado_general) con todo arriba"
  else
    pendiente "CA-2.10 (estado_general OK)" "saga-log está '$(campo componentes.saga-log.estado)' (US-01 todavía no existe): estado_general es $(campo estado_general)"
  fi

  # Proveedor: acreditación creada y aprobada por el BFF.
  local proveedor acr
  proveedor="$(uuid_nuevo)"
  http POST /acreditaciones "{\"proveedor_id\":\"$proveedor\",\"pais\":\"CO\",\"ciudad\":\"Bogota\",\"categorias\":[\"PLOMERIA\"],\"nivel\":\"ORO\",\"vigencia_meses\":12,\"motivo\":\"verificacion bff\"}"
  acr="$(campo id)"
  http PUT "/acreditaciones/$acr/aprobar" '{"motivo":"verificacion bff"}'
  http GET "/proveedores/$acr/completo"
  if [ "$CODIGO" = "200" ] && [ "$(campo proveedor_id)" = "$proveedor" ] && [ "$(campo partes.acreditacion.estado)" = "DISPONIBLE" ]; then
    criterio CA-2.8 0 "GET /proveedores/$acr/completo → 200 con la acreditación del proveedor $proveedor"
  else
    criterio CA-2.8 1 "se esperaba 200 con proveedor_id=$proveedor; llegó $CODIGO: $CUERPO"
  fi

  local url
  for url in "/trabajos/$id/completo" "/proveedores/$acr/completo" "/estado-del-sistema"; do
    if "$PYTHON" "$RAIZ/herramientas/medir_latencia.py" "$URL_BFF$url" --peticiones 50 --concurrencia 5 --umbral-p95-ms 2000 >>"$SALIDA" 2>&1; then
      criterio CA-2.11 0 "p95 de GET $url < 2000 ms (50 peticiones, concurrencia 5)"
    else
      criterio CA-2.11 1 "p95 de GET $url no cumplió los 2000 ms — ver $SALIDA"
    fi
  done
}

# ------------------------------------------------------------------ US3
TOPICO_TRABAJO='persistent://hogar-alpes/trabajos/evt-trabajo-andina'
TOPICO_EMPAREJAMIENTO='persistent://hogar-alpes/emparejamiento/evt-emparejamiento'
TOPICO_ACREDITACION='persistent://hogar-alpes/acreditacion/evt-acreditacion'
SUSCRIPCION_TEMPORAL='verif-cid'

# tiene_lineas CONTENEDOR → 0 si LINEAS trae registros de ese servicio (prefijo `servicio-N |`)
tiene_lineas() { printf '%s\n' "$LINEAS" | grep -Eq "^$1-[0-9]+ +\|"; }
primera_linea() { printf '%s\n' "$LINEAS" | grep -En "^$1-[0-9]+ +\|" | head -1 | cut -d: -f1; }

# buscar_cid CID → deja en LINEAS los registros de todos los contenedores con ese cid, en orden de tiempo
buscar_cid() {
  LINEAS="$(compose logs --no-color -t 2>&1 | grep -F "cid=$1" | sort -t'|' -k2)"
}

# valor_cid SERVICIO TRABAJO_ID → el `cid=` de la primera línea de ese contenedor con ese trabajo
valor_cid() {
  compose logs --no-color -t 2>&1 | grep -E "^$1-[0-9]+ +\|" | grep -F "trabajo_id=$2" | head -1 \
    | sed -n 's/.*cid=\([^ ]*\).*/\1/p'
}

# contadores_particion TOPICO → "particion mensajes" por línea, de `partitioned-stats`
contadores_particion() {
  compose exec -T broker-1 bin/pulsar-admin topics partitioned-stats "$1" --per-partition 2>/dev/null | "$PYTHON" -c '
import json, sys
try:
    datos = json.load(sys.stdin)
    for nombre, estadistica in sorted(datos.get("partitions", {}).items()):
        print(nombre.rsplit("-", 1)[-1], estadistica.get("msgInCounter", 0))
except Exception:
    pass
'
}

# consumir_uno TOPICO → la línea `key:[…], properties:[…], content:…` del primer mensaje de la suscripción temporal
consumir_uno() {
  local limite=()
  command -v timeout >/dev/null 2>&1 && limite=(timeout 60)
  "${limite[@]}" "${COMPOSE[@]}" exec -T broker-1 bin/pulsar-client consume "$1" -s "$SUSCRIPCION_TEMPORAL" -n 1 2>&1 \
    | grep -a 'properties:\[' | head -1
}

crear_suscripciones_temporales() {
  local topico
  SUSCRIPCIONES_CREADAS=1
  for topico in "$TOPICO_TRABAJO" "$TOPICO_EMPAREJAMIENTO" "$TOPICO_ACREDITACION"; do
    compose exec -T broker-1 bin/pulsar-admin topics create-subscription "$topico" \
      -s "$SUSCRIPCION_TEMPORAL" --messageId latest >>"$SALIDA" 2>&1
  done
}

borrar_suscripciones_temporales() {
  local topico
  SUSCRIPCIONES_CREADAS=0
  for topico in "$TOPICO_TRABAJO" "$TOPICO_EMPAREJAMIENTO" "$TOPICO_ACREDITACION"; do
    compose exec -T broker-1 bin/pulsar-admin topics unsubscribe "$topico" -s "$SUSCRIPCION_TEMPORAL" >>"$SALIDA" 2>&1 || true
  done
}

# Cadena de un trabajo: CA-2.17c y CA-2.18. Deja ID, CID y CONTADORES_ANTES.
us3_cadena() {
  resultado "### Cadena de un trabajo creado por el BFF (CA-2.17c, CA-2.18)"
  CONTADORES_ANTES="$(contadores_particion "$TOPICO_TRABAJO")"

  http POST /trabajos "$CUERPO_TRABAJO"
  ID="$(campo id)"
  CID="$(campo correlation_id)"
  local cabecera_cid
  cabecera_cid="$(cabecera X-Correlation-Id)"
  if [ "$CODIGO" = "202" ] && [ -n "$CID" ] && [ "$CID" = "$cabecera_cid" ]; then
    criterio CA-2.17c 0 "el correlation_id del cuerpo ($CID) es el mismo de la cabecera X-Correlation-Id"
  else
    criterio CA-2.17c 1 "cuerpo='$CID' cabecera='$cabecera_cid' código=$CODIGO"
    return 1
  fi

  # Consistencia eventual: se espera a que Emparejamiento y Operaciones escriban su paso.
  local i
  for ((i = 0; i < 20; i++)); do
    buscar_cid "$CID"
    tiene_lineas operaciones-consumidor && tiene_lineas emparejamiento-andina && break
    sleep 1
  done

  local faltan="" servicio
  for servicio in bff gestion-trabajos operaciones-consumidor emparejamiento-andina; do
    tiene_lineas "$servicio" || faltan="$faltan $servicio"
  done
  if [ -z "$faltan" ]; then
    criterio CA-2.18 0 "una sola búsqueda de $CID trae líneas de bff, gestion-trabajos, operaciones-consumidor y emparejamiento-andina"
  else
    criterio CA-2.18 1 "faltan pasos en la búsqueda de $CID:$faltan"
  fi

  local n_creacion n_seguimiento n_emparejamiento
  n_creacion="$(primera_linea gestion-trabajos)"
  n_seguimiento="$(primera_linea operaciones-consumidor)"
  n_emparejamiento="$(primera_linea emparejamiento-andina)"
  if [ -n "$n_creacion" ] && [ -n "$n_seguimiento" ] && [ -n "$n_emparejamiento" ] \
     && [ "$n_creacion" -lt "$n_seguimiento" ] && [ "$n_creacion" -lt "$n_emparejamiento" ]; then
    criterio CA-2.18 0 "el orden por marca de tiempo es coherente: la creación aparece antes que el seguimiento y el emparejamiento"
  else
    criterio CA-2.18 1 "orden incoherente (creación=$n_creacion seguimiento=$n_seguimiento emparejamiento=$n_emparejamiento)"
  fi

  if tiene_lineas gestion-trabajos-consumidor; then
    criterio CA-2.18 1 "gestion-trabajos-consumidor trae líneas de una petición que no pasó por él: el camino real cambió"
  else
    criterio CA-2.18 0 "gestion-trabajos-consumidor no trae líneas (POST /trabajos se ejecuta en la API; solo atiende cmd-trabajo-*)"
  fi
  pendiente "CA-2.18 (paso saga-log)" "saga-log (US-01) todavía no existe"
}

# Vida de un trabajo entre peticiones: FR-028b y SC-013, más la partición (CA-2.20).
us3_vida_del_trabajo() {
  resultado "### Vida del trabajo entre peticiones (FR-028b) y partición (CA-2.20)"
  http PUT "/trabajos/$ID/estado" '{"estado":"EMPAREJANDO"}'
  local cid2 codigo2="$CODIGO"
  cid2="$(cabecera X-Correlation-Id)"
  http PUT "/trabajos/$ID/estado" '{"estado":"ASIGNADO"}'
  local cid3 codigo3="$CODIGO"
  cid3="$(cabecera X-Correlation-Id)"
  sleep 3

  local del_trabajo distintos
  del_trabajo="$(compose logs --no-color -t 2>&1 | grep -F "trabajo_id=$ID")"
  distintos="$(printf '%s\n' "$del_trabajo" | sed -n 's/.*cid=\([^ ]*\) trabajo_id=.*/\1/p' | sort -u | wc -l | tr -d ' ')"
  if [ "$codigo2" = "202" ] && [ "$codigo3" = "202" ] && [ "$distintos" -ge 3 ] \
     && printf '%s\n' "$del_trabajo" | grep -qF "cid=$CID" \
     && printf '%s\n' "$del_trabajo" | grep -qF "cid=$cid2" \
     && printf '%s\n' "$del_trabajo" | grep -qF "cid=$cid3"; then
    criterio FR-028b 0 "grep trabajo_id=$ID muestra las 3 peticiones del trabajo, cada una con su propio cid ($distintos valores distintos)"
  else
    criterio FR-028b 1 "PUT=$codigo2/$codigo3, cids distintos=$distintos (se esperaban >= 3 con $CID, $cid2 y $cid3)"
  fi

  buscar_cid "$CID"
  if printf '%s\n' "$LINEAS" | grep -qF "PUT /trabajos/$ID/estado"; then
    criterio FR-028b 1 "la búsqueda de $CID (la creación) trae líneas de las peticiones PUT posteriores"
  else
    criterio FR-028b 0 "la búsqueda de $CID (la creación) no trae las líneas de las peticiones PUT posteriores"
  fi

  local despues veredicto
  despues="$(contadores_particion "$TOPICO_TRABAJO")"
  veredicto="$(printf 'ANTES\n%s\nDESPUES\n%s\n' "$CONTADORES_ANTES" "$despues" | "$PYTHON" -c '
import sys
seccion, antes, despues = None, {}, {}
for linea in sys.stdin.read().splitlines():
    if linea in ("ANTES", "DESPUES"):
        seccion = linea
        continue
    if not linea.strip():
        continue
    particion, contador = linea.split()
    (antes if seccion == "ANTES" else despues)[particion] = int(contador)
delta = {p: despues.get(p, 0) - antes.get(p, 0) for p in despues}
con_mensajes = {p: d for p, d in delta.items() if d}
print("OK" if len(con_mensajes) == 1 and list(con_mensajes.values()) == [3] else "MAL " + str(delta))
')"
  if [ "$veredicto" = "OK" ]; then
    criterio CA-2.20 0 "los 3 mensajes del trabajo $ID (creación y dos cambios de estado) cayeron en UNA sola partición de evt-trabajo-andina"
  else
    criterio CA-2.20 1 "los mensajes del trabajo no cayeron en una sola partición: $veredicto"
  fi
}

# Flujo sin trabajo: acreditar un proveedor con un identificador elegido por el cliente.
us3_acreditacion() {
  resultado "### Cadena de una acreditación (FR-028, flujo sin trabajo)"
  PROVEEDOR="$(uuid_nuevo)"
  CID_ACR="cid-acred-$RANDOM"
  http POST /acreditaciones "{\"proveedor_id\":\"$PROVEEDOR\",\"pais\":\"CO\",\"ciudad\":\"Bogota\",\"categorias\":[\"PLOMERIA\"],\"nivel\":\"ORO\",\"vigencia_meses\":12,\"motivo\":\"verificacion bff\"}" -H "X-Correlation-Id: $CID_ACR"
  local acr devuelto
  acr="$(campo id)"
  devuelto="$(cabecera X-Correlation-Id)"
  http PUT "/acreditaciones/$acr/aprobar" '{"motivo":"verificacion bff"}' -H "X-Correlation-Id: $CID_ACR"
  if [ "$devuelto" = "$CID_ACR" ] && [ "$CODIGO" = "202" ]; then
    criterio CA-2.16 0 "el BFF respetó el X-Correlation-Id del cliente ($CID_ACR)"
  else
    criterio CA-2.16 1 "se esperaba $CID_ACR y llegó '$devuelto' (aprobar → $CODIGO)"
  fi

  local i visto=0
  for ((i = 0; i < 10; i++)); do
    http GET "$RUTA_CANDIDATOS"
    if printf '%s' "$CUERPO" | grep -qF "$PROVEEDOR"; then visto=1; break; fi
    sleep 1
  done
  if [ "$visto" = 1 ]; then
    criterio CA-2.18 0 "GET /candidatos muestra al proveedor: la cadena real corrió, no solo los registros"
  else
    criterio CA-2.18 1 "el proveedor $PROVEEDOR no apareció en /candidatos tras 10 s"
  fi

  buscar_cid "$CID_ACR"
  local faltan="" servicio
  for servicio in bff acreditacion emparejamiento-proyeccion; do
    tiene_lineas "$servicio" || faltan="$faltan $servicio"
  done
  if [ -z "$faltan" ]; then
    criterio CA-2.18 0 "la búsqueda de $CID_ACR trae líneas de bff, acreditacion y emparejamiento-proyeccion"
  else
    criterio CA-2.18 1 "faltan pasos en la búsqueda de $CID_ACR:$faltan"
  fi
  if tiene_lineas acreditacion-consumidor || tiene_lineas gestion-trabajos-consumidor; then
    criterio CA-2.18 1 "un consumidor que no debía intervenir trae líneas de la acreditación: el camino real cambió"
  else
    criterio CA-2.18 0 "acreditacion-consumidor y gestion-trabajos-consumidor no traen líneas (solo atienden cmd-*)"
  fi
}

# Mensajes reales del broker: CA-2.19 y SC-008.
us3_broker() {
  resultado "### Mensajes reales del broker (CA-2.19)"
  local mensaje cuantas

  mensaje="$(consumir_uno "$TOPICO_TRABAJO")"
  cuantas="$(printf '%s' "$mensaje" | grep -ao "$CID" | wc -l | tr -d ' ')"
  if printf '%s' "$mensaje" | grep -qF "key:[$ID]" && printf '%s' "$mensaje" | grep -qF "correlation_id=$CID" && [ "$cuantas" -ge 2 ]; then
    criterio CA-2.19 0 "evt-trabajo-andina: clave=trabajo_id, propiedad correlation_id=$CID y el mismo valor en el sobre ($cuantas apariciones)"
  else
    criterio CA-2.19 1 "evt-trabajo-andina: no cumple (clave/propiedad/sobre). Mensaje: ${mensaje:0:300}"
  fi

  mensaje="$(consumir_uno "$TOPICO_EMPAREJAMIENTO")"
  cuantas="$(printf '%s' "$mensaje" | grep -ao "$CID" | wc -l | tr -d ' ')"
  if printf '%s' "$mensaje" | grep -qF "key:[$ID]" && printf '%s' "$mensaje" | grep -qF "correlation_id=$CID" && [ "$cuantas" -ge 2 ]; then
    criterio CA-2.19 0 "evt-emparejamiento: clave=trabajo_id, propiedad correlation_id=$CID y el mismo valor en el sobre ($cuantas apariciones)"
  else
    criterio CA-2.19 1 "evt-emparejamiento: no cumple (clave/propiedad/sobre). Mensaje: ${mensaje:0:300}"
  fi

  mensaje="$(consumir_uno "$TOPICO_ACREDITACION")"
  cuantas="$(printf '%s' "$mensaje" | grep -ao "$CID_ACR" | wc -l | tr -d ' ')"
  if printf '%s' "$mensaje" | grep -qF "key:[$PROVEEDOR]" && printf '%s' "$mensaje" | grep -qF "correlation_id=$CID_ACR" && [ "$cuantas" -ge 2 ]; then
    criterio CA-2.19 0 "evt-acreditacion: clave=proveedor_id, propiedad correlation_id=$CID_ACR y el mismo valor en el sobre ($cuantas apariciones)"
  else
    criterio CA-2.19 1 "evt-acreditacion: no cumple (clave/propiedad/sobre). Mensaje: ${mensaje:0:300}"
  fi
}

# Sin pasar por el BFF: CA-2.22.
us3_sin_bff() {
  resultado "### Peticiones y mensajes que no pasan por el BFF (CA-2.22)"
  local url_gt="http://localhost:${PUERTO_TRABAJOS:-8000}" directa cid_directo
  directa="$(curl -si -X POST "$url_gt/trabajos" -H 'Content-Type: application/json' --data "$CUERPO_TRABAJO" 2>/dev/null | tr -d '\r')"
  cid_directo="$(printf '%s\n' "$directa" | grep -i '^x-correlation-id:' | head -1 | sed 's/^[^:]*: *//')"
  sleep 2
  if [ -n "$cid_directo" ] && compose logs --no-color -t gestion-trabajos 2>&1 | grep -qF "cid=$cid_directo"; then
    criterio CA-2.22a 0 "POST directo a Gestión de Trabajos, sin cabecera: devolvió X-Correlation-Id=$cid_directo y aparece en sus registros"
  else
    criterio CA-2.22a 1 "la llamada directa no quedó identificada (cabecera='$cid_directo')"
  fi

  # Un mensaje publicado SIN correlation_id, por el camino real (el contrato de la propia API).
  local id2
  id2="$(uuid_nuevo)"
  compose exec -T -e ID2="$id2" gestion-trabajos-consumidor python - >>"$SALIDA" 2>&1 <<'PUBLICAR'
import os, time, uuid
from gestion_trabajos.config.broker import productor
from gestion_trabajos.modulos.trabajos.infraestructura.schema.v1.eventos import TIPO_CREADO, EventoTrabajo

trabajo_id = os.environ['ID2']
ahora = int(time.time() * 1000)
evento = EventoTrabajo(
    id=str(uuid.uuid4()), time=ahora, ingestion=ahora, specversion='1.0', type=TIPO_CREADO,
    datacontenttype='application/avro', service_name='verificador-bff', correlation_id=None,
    trabajo_id=trabajo_id, partner_id='verificador', canal='MARKETPLACE', pais='CO', ciudad='Bogota',
    categoria='PLOMERIA', urgencia='NORMAL', estado='CREADO', estado_anterior='',
)
productor('persistent://hogar-alpes/trabajos/evt-trabajo-andina', EventoTrabajo).send(evento, partition_key=trabajo_id)
print('publicado sin correlation_id:', trabajo_id)
PUBLICAR
  local cid_ops="" cid_emp="" i
  for ((i = 0; i < 20; i++)); do
    cid_ops="$(valor_cid operaciones-consumidor "$id2")"
    cid_emp="$(valor_cid emparejamiento-andina "$id2")"
    [ -n "$cid_ops" ] && [ -n "$cid_emp" ] && break
    sleep 1
  done
  # Cada suscripción recibe el mensaje por su cuenta: cada una crea su propio identificador.
  if [ -n "$cid_ops" ] && [ "$cid_ops" != "-" ] && [ -n "$cid_emp" ] && [ "$cid_emp" != "-" ]; then
    criterio CA-2.22b 0 "un mensaje sin correlation_id quedó identificado por quien lo recibió: operaciones=$cid_ops emparejamiento=$cid_emp"
  else
    criterio CA-2.22b 1 "operaciones='$cid_ops' emparejamiento='$cid_emp' (se esperaba un identificador creado, distinto de '-')"
    return
  fi
  if compose logs --no-color -t emparejamiento-andina 2>&1 | grep -F "cid=$cid_emp" | grep -q 'Publicado en'; then
    criterio CA-2.22b 0 "el mensaje que Emparejamiento publicó después lleva el identificador que él creó ($cid_emp)"
  else
    criterio CA-2.22b 1 "Emparejamiento no publicó con el identificador creado ($cid_emp)"
  fi
}

# Escenario 8 sin modificar: la clave de partición no cambió (CA-2.20).
us3_escenario_8() {
  if [ "${ESCENARIO_8:-si}" = "omitir" ]; then
    pendiente "CA-2.20 (escenario-8.sh)" "omitido por ESCENARIO_8=omitir"
    return
  fi
  if [ -n "$(git -C "$RAIZ" diff --stat -- escenarios/escenario-8.sh)" ]; then
    criterio CA-2.20 1 "escenarios/escenario-8.sh fue modificado: debe correr sin cambios"
    return
  fi
  resultado "  corriendo escenarios/escenario-8.sh sin modificarlo (${ESCENARIO_8_ARGS:---proveedores 10000 --trabajos 500})…"
  # shellcheck disable=SC2086
  if bash "$RAIZ/escenarios/escenario-8.sh" ${ESCENARIO_8_ARGS:---proveedores 10000 --trabajos 500} >>"$SALIDA" 2>&1; then
    criterio CA-2.20 0 "escenario-8.sh sigue pasando sin cambios"
  else
    criterio CA-2.20 1 "escenario-8.sh falló — ver $SALIDA"
  fi
}

seccion_us3() {
  resultado "## US3 · Reconstruir una petición con una sola búsqueda (CA-2.16…CA-2.22)"
  if ! command -v docker >/dev/null 2>&1; then
    pendiente "CA-2.18" "docker no está disponible: no se pueden leer los registros ni el broker"
    return
  fi
  local ID="" CID="" PROVEEDOR="" CID_ACR="" CONTADORES_ANTES="" LINEAS=""
  crear_suscripciones_temporales
  if us3_cadena; then
    us3_vida_del_trabajo
    us3_acreditacion
    us3_broker
  fi
  borrar_suscripciones_temporales
  us3_sin_bff
  us3_escenario_8
}

# ------------------------------------------------------------- ejecución
for seccion in $SECCIONES; do
  resultado ""
  "seccion_$seccion"
done

resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then
  resultado "FALLA · $fallos criterio(s) no se cumplieron, $pendientes pendiente(s) · detalle en $SALIDA"
  exit 1
fi
if [ "$pendientes" -gt 0 ]; then
  resultado "PASA con PENDIENTES · sin fallos, $pendientes criterio(s) sin ejecutar · detalle en $SALIDA"
  exit 0
fi
resultado "PASA · BFF completo · detalle en $SALIDA"
