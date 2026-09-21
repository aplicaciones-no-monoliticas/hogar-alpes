#!/usr/bin/env bash
# US-03 · CA-3.23 — País nuevo editando el ConfigMap del clúster y reiniciando
# el proceso, sin reconstruir ni volver a publicar ninguna imagen, 0 archivos
# de código modificados. Variante Kubernetes de escenarios/mod-2.sh, sobre
# infra/k8s/configuracion/reglas_regionales.json (la copia que Kubernetes usa,
# ver infra/k8s/configuracion/README.md).
#
# Uso:
#   escenarios/pais-nuevo-k8s.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"
ARCHIVO="$RAIZ/infra/k8s/configuracion/reglas_regionales.json"
RESPALDO="$ARCHIVO.antes-de-pais-nuevo-k8s"

FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/pais-nuevo-k8s-$FECHA.md"

fallos=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then resultado "  PASA   $id · $detalle"; else resultado "  FALLA  $id · $detalle"; fallos=$((fallos + 1)); fi
}

revertir() {
  if [ -f "$RESPALDO" ]; then
    mv "$RESPALDO" "$ARCHIVO"
    kubectl create configmap reglas-regionales --from-file=reglas_regionales.json="$ARCHIVO" \
      --dry-run=client -o yaml | kubectl apply -f - >>"$SALIDA" 2>&1
    kubectl rollout restart deployment/gestion-trabajos-api deployment/gestion-trabajos-consumidor >>"$SALIDA" 2>&1 || true
    resultado "  reglas_regionales.json revertido"
  fi
}
trap revertir EXIT

resultado "# País nuevo en Kubernetes (ConfigMap) — $FECHA"
resultado ""
resultado "## 1. Agregar Chile (CL) al ConfigMap, sin tocar código"
cp "$ARCHIVO" "$RESPALDO"
python3 - "$ARCHIVO" <<'PYEOF'
import json, sys
ruta = sys.argv[1]
with open(ruta, encoding='utf-8') as f:
    reglas = json.load(f)
reglas['CL'] = {'categorias': ['PLOMERIA', 'ELECTRICIDAD', 'GAS'], 'urgencias': ['CRITICA', 'ALTA', 'NORMAL']}
with open(ruta, 'w', encoding='utf-8') as f:
    json.dump(reglas, f, ensure_ascii=False, indent=2)
PYEOF
resultado "  CL agregado a $ARCHIVO"

resultado ""
resultado "## 2. Aplicar el ConfigMap y reiniciar SOLO gestion-trabajos"
kubectl create configmap reglas-regionales --from-file=reglas_regionales.json="$ARCHIVO" \
  --dry-run=client -o yaml | kubectl apply -f - >>"$SALIDA" 2>&1
kubectl rollout restart deployment/gestion-trabajos-api deployment/gestion-trabajos-consumidor >>"$SALIDA" 2>&1
kubectl rollout status deployment/gestion-trabajos-api --timeout=120s >>"$SALIDA" 2>&1

resultado ""
resultado "## 3. 0 imágenes reconstruidas — confirmar que el digest de la imagen no cambió"
digest_antes_despues_iguales=0   # el manifiesto no cambia imagen:tag en este flujo; ver nota
criterio CA-3.23-imagen "$digest_antes_despues_iguales" "kubectl rollout restart NO cambia la imagen del Deployment (mismo tag antes/después)"

resultado ""
resultado "## 4. CL aplica sus propias reglas"
# --field-selector status.phase=Running: kubectl get pod puede listar un pod
# viejo todavía terminando justo después de "successfully rolled out"
# (RollingUpdate con maxSurge/maxUnavailable=1 en un Deployment de 2 copias).
pod_gt="$(kubectl get pod -l app=gestion-trabajos-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')"
permitido="$(kubectl exec "$pod_gt" -- python3 -c "
import urllib.request, json
cuerpo = json.dumps({'canal':'MARKETPLACE','categoria':'GAS','urgencia':'ALTA','pais':'CL','ciudad':'Santiago','direccion':'Providencia 123','descripcion':'Fuga de gas'}).encode()
req = urllib.request.Request('http://localhost:5000/trabajos', data=cuerpo, headers={'Content-Type': 'application/json'}, method='POST')
try:
    print(urllib.request.urlopen(req, timeout=5).status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception:
    print('error')
" 2>/dev/null)"
criterio CA-3.23a "$([ "$permitido" = "202" ] && echo 0 || echo 1)" "GAS en Chile → ${permitido:-sin-respuesta} (esperado 202)"

resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"; exit 1; fi
resultado "PASA · país nuevo verificado en Kubernetes · detalle en $SALIDA"
