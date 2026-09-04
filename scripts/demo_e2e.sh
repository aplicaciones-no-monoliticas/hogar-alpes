#!/usr/bin/env bash
# Guion de demostración E2E — ver docs/ESCENARIOS_E2E.md para el detalle de
# qué evidencia cada escenario.
#
# Requiere: curl. No requiere jq ni Python.
# Uso: bash scripts/demo_e2e.sh [BASE_URL]
#      BASE_URL por defecto: http://localhost:5000

set -u

BASE_URL="${1:-${BASE_URL:-http://localhost:5000}}"

VERDE='\033[0;32m'
ROJO='\033[0;31m'
AMARILLO='\033[1;33m'
NEGRITA='\033[1m'
RESET='\033[0m'

TOTAL=0
EXITOSOS=0

seccion() {
  echo
  echo -e "${NEGRITA}== $1 ==${RESET}"
}

# Hace un request y deja el cuerpo en $HTTP_BODY y el código en $HTTP_STATUS.
peticion() {
  local metodo="$1" ruta="$2" datos="${3:-}"
  local respuesta
  if [ -n "$datos" ]; then
    respuesta=$(curl -s -w '\n%{http_code}' -X "$metodo" "$BASE_URL$ruta" \
      -H 'Content-Type: application/json' -d "$datos")
  else
    respuesta=$(curl -s -w '\n%{http_code}' -X "$metodo" "$BASE_URL$ruta")
  fi
  HTTP_STATUS=$(echo "$respuesta" | tail -n1)
  HTTP_BODY=$(echo "$respuesta" | sed '$d')
}

# Extrae "campo": "valor" o "campo": valor de un JSON plano (sin anidar).
campo() {
  local json="$1" nombre="$2"
  echo "$json" | sed -n "s/.*\"$nombre\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^\",}]*\)\"\{0,1\}.*/\1/p" | head -n1
}

verificar_status() {
  local descripcion="$1" esperado="$2" obtenido="$3"
  TOTAL=$((TOTAL + 1))
  if [ "$esperado" == "$obtenido" ]; then
    echo -e "  ${VERDE}[OK]${RESET} $descripcion (HTTP $obtenido)"
    EXITOSOS=$((EXITOSOS + 1))
  else
    echo -e "  ${ROJO}[FALLA]${RESET} $descripcion (esperado HTTP $esperado, obtuvo $obtenido)"
    echo "         cuerpo: $HTTP_BODY"
  fi
}

verificar_campo() {
  local descripcion="$1" esperado="$2" obtenido="$3"
  TOTAL=$((TOTAL + 1))
  if [ "$esperado" == "$obtenido" ]; then
    echo -e "  ${VERDE}[OK]${RESET} $descripcion"
    EXITOSOS=$((EXITOSOS + 1))
  else
    echo -e "  ${ROJO}[FALLA]${RESET} $descripcion (esperado '$esperado', obtuvo '$obtenido')"
  fi
}

echo -e "${NEGRITA}Guion de demostración E2E — Gestión de Trabajos${RESET}"
echo "Base URL: $BASE_URL"
echo "Detalle narrativo de cada escenario: docs/ESCENARIOS_E2E.md"

# ---------------------------------------------------------------------------
seccion "0. Salud del servicio"
peticion GET /health
verificar_status "El servicio responde" 200 "$HTTP_STATUS"
verificar_campo "status es 'up'" "up" "$(campo "$HTTP_BODY" status)"

# ---------------------------------------------------------------------------
seccion "1. Crear un trabajo válido (CO, SINIESTRO_GRANIZO, CRITICA) — CQS escritura"
peticion POST /trabajos '{
  "canal": "B2B2C", "partner_id": "seguros-alpes", "referencia_externa": "SIN-99123",
  "categoria": "SINIESTRO_GRANIZO", "urgencia": "CRITICA",
  "pais": "CO", "ciudad": "Bogota", "direccion": "Cra 7 # 71-21",
  "descripcion": "Granizada: techo perforado"
}'
verificar_status "El comando se acepta (202, no 200/201)" 202 "$HTTP_STATUS"
TRABAJO_ID=$(campo "$HTTP_BODY" id)
if [ -z "$TRABAJO_ID" ]; then
  echo -e "  ${ROJO}No se obtuvo un id de trabajo — se detiene el guion (los pasos siguientes dependen de él).${RESET}"
  echo -e "${AMARILLO}Resumen: $EXITOSOS/$TOTAL escenarios superados${RESET}"
  exit 1
fi
echo "  id capturado: $TRABAJO_ID"

# ---------------------------------------------------------------------------
seccion "2. Leer el trabajo creado — CQS lectura"
peticion GET "/trabajos/$TRABAJO_ID"
verificar_status "La consulta responde 200" 200 "$HTTP_STATUS"
verificar_campo "estado inicial es CREADO" "CREADO" "$(campo "$HTTP_BODY" estado)"

# ---------------------------------------------------------------------------
seccion "3. El módulo operaciones ya abrió su seguimiento — evento de dominio 'gordo'"
peticion GET "/trabajos/$TRABAJO_ID/seguimiento"
verificar_status "El seguimiento ya existe (200), sin llamada explícita" 200 "$HTTP_STATUS"
verificar_campo "prioridad P1 por urgencia CRITICA" "P1" "$(campo "$HTTP_BODY" prioridad)"
verificar_campo "SLA de 60 minutos" "60" "$(campo "$HTTP_BODY" minutos_sla)"

# ---------------------------------------------------------------------------
seccion "4. Transición de estado válida (CREADO -> EMPAREJANDO)"
peticion PUT "/trabajos/$TRABAJO_ID/estado" '{"estado":"EMPAREJANDO"}'
verificar_status "La transición se acepta" 202 "$HTTP_STATUS"

peticion GET "/trabajos/$TRABAJO_ID"
verificar_campo "el estado quedó en EMPAREJANDO" "EMPAREJANDO" "$(campo "$HTTP_BODY" estado)"

# ---------------------------------------------------------------------------
seccion "5. El seguimiento se actualiza solo (evento EstadoTrabajoCambiado)"
peticion GET "/trabajos/$TRABAJO_ID/seguimiento"
verificar_status "El seguimiento sigue respondiendo 200" 200 "$HTTP_STATUS"
verificar_campo "estado_trabajo reflejado sin llamada directa" "EMPAREJANDO" "$(campo "$HTTP_BODY" estado_trabajo)"

# ---------------------------------------------------------------------------
seccion "6. Transición de estado inválida (EMPAREJANDO -> COMPLETADO)"
peticion PUT "/trabajos/$TRABAJO_ID/estado" '{"estado":"COMPLETADO"}'
verificar_status "La regla de negocio rechaza el salto de estado" 409 "$HTTP_STATUS"

# ---------------------------------------------------------------------------
seccion "7. Categoría no permitida en la región (SINIESTRO_GRANIZO en MX)"
peticion POST /trabajos '{
  "categoria": "SINIESTRO_GRANIZO", "urgencia": "ALTA",
  "pais": "MX", "ciudad": "CDMX", "direccion": "Reforma 100"
}'
verificar_status "El sidecar regional de MX rechaza la categoría" 400 "$HTTP_STATUS"

# ---------------------------------------------------------------------------
seccion "8. Ubicación incompleta"
peticion POST /trabajos '{
  "categoria": "PLOMERIA", "urgencia": "NORMAL",
  "pais": "CO", "ciudad": "", "direccion": ""
}'
verificar_status "La regla UbicacionCompleta rechaza el trabajo" 400 "$HTTP_STATUS"

# ---------------------------------------------------------------------------
seccion "9. Consulta por estado (colección) — CQS lectura con filtro"
peticion GET "/trabajos?estado=EMPAREJANDO"
verificar_status "La consulta por estado responde 200" 200 "$HTTP_STATUS"

# ---------------------------------------------------------------------------
seccion "10. Trabajo inexistente"
peticion GET "/trabajos/00000000-0000-0000-0000-000000000000"
verificar_status "Se responde 404, no un error de servidor" 404 "$HTTP_STATUS"

# ---------------------------------------------------------------------------
seccion "11. Comando asíncrono vía Pulsar (manual)"
echo "  No automatizado: curl no habla el protocolo binario de Pulsar."
echo "  Ver 'Escenario 11' en docs/ESCENARIOS_E2E.md para el paso a paso."

# ---------------------------------------------------------------------------
echo
if [ "$EXITOSOS" -eq "$TOTAL" ]; then
  echo -e "${VERDE}${NEGRITA}Resumen: $EXITOSOS/$TOTAL escenarios superados${RESET}"
else
  echo -e "${ROJO}${NEGRITA}Resumen: $EXITOSOS/$TOTAL escenarios superados${RESET}"
fi
[ "$EXITOSOS" -eq "$TOTAL" ]
