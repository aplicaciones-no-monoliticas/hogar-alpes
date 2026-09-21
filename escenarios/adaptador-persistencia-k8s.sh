#!/usr/bin/env bash
# US-03 · CA-3.24 — Adaptador de persistencia: cambiar la variable que elige
# cómo guarda sus datos Gestión de Trabajos funciona igual que en Compose.
# Variante Kubernetes de escenarios/mod-1.sh, parte dinámica (la parte
# estática — que el commit no toca dominio/aplicacion — ya la cubre mod-1.sh
# contra el código, que no cambia entre entornos).
#
# Uso:
#   escenarios/adaptador-persistencia-k8s.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"
FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/adaptador-persistencia-k8s-$FECHA.md"

fallos=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then resultado "  PASA   $id · $detalle"; else resultado "  FALLA  $id · $detalle"; fallos=$((fallos + 1)); fi
}

resultado "# Adaptador de persistencia en Kubernetes — $FECHA"
resultado ""
resultado "## 1. Cambiar ADAPTADOR_TRABAJOS a 'memoria' en el Deployment (WORKERS=1, mismo motivo que mod-1.sh)"
kubectl set env deployment/gestion-trabajos-api ADAPTADOR_TRABAJOS=memoria WORKERS=1 >>"$SALIDA" 2>&1
kubectl rollout status deployment/gestion-trabajos-api --timeout=120s >>"$SALIDA" 2>&1

resultado ""
resultado "## 2. Crear un trabajo y confirmar que responde con el adaptador en memoria"
pod_gt="$(kubectl get pod -l app=gestion-trabajos-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')"
codigo="$(kubectl exec "$pod_gt" -- python3 -c "
import urllib.request, json
cuerpo = json.dumps({'canal':'MARKETPLACE','categoria':'PLOMERIA','urgencia':'ALTA','pais':'CO','ciudad':'Bogota','direccion':'Calle 1','descripcion':'Prueba adaptador memoria'}).encode()
req = urllib.request.Request('http://localhost:5000/trabajos', data=cuerpo, headers={'Content-Type': 'application/json'}, method='POST')
try:
    print(urllib.request.urlopen(req, timeout=5).status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception:
    print('error')
" 2>/dev/null)"
criterio CA-3.24a "$([ "$codigo" = "202" ] && echo 0 || echo 1)" "POST /trabajos con adaptador memoria → ${codigo:-sin-respuesta} (esperado 202)"

resultado ""
resultado "## 3. Revertir a postgres"
kubectl set env deployment/gestion-trabajos-api ADAPTADOR_TRABAJOS=postgres WORKERS=2 >>"$SALIDA" 2>&1
kubectl rollout status deployment/gestion-trabajos-api --timeout=120s >>"$SALIDA" 2>&1
resultado "  revertido a ADAPTADOR_TRABAJOS=postgres"

resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"; exit 1; fi
resultado "PASA · adaptador de persistencia verificado en Kubernetes · detalle en $SALIDA"
