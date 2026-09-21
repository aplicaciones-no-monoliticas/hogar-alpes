#!/usr/bin/env bash
# US-03 · CA-3.22 — Región nueva en caliente sin interrumpir las activas.
# Reutiliza infra/pulsar/agregar-region.sh TAL CUAL (research.md Decisión 5),
# corrido dentro del clúster vía un Job puntual, y despliega el Deployment de
# la región nueva (infra/k8s/servicios/emparejamiento-conosur.yaml).
#
# Uso:
#   escenarios/region-nueva-k8s.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$DIR/.." && pwd)"
FECHA="$(date +%Y%m%d-%H%M%S)"
DIR_RESULTADOS="$RAIZ/docs/resultados"
mkdir -p "$DIR_RESULTADOS"
SALIDA="$DIR_RESULTADOS/region-nueva-k8s-$FECHA.md"

fallos=0
resultado() { echo "$1" | tee -a "$SALIDA"; }
criterio() {
  local id="$1" ok="$2" detalle="$3"
  if [ "$ok" = "0" ]; then resultado "  PASA   $id · $detalle"; else resultado "  FALLA  $id · $detalle"; fallos=$((fallos + 1)); fi
}

resultado "# Región nueva en caliente en Kubernetes — $FECHA"
resultado ""
resultado "## 1. Las regiones activas responden antes del cambio"
for region in andina norteamerica; do
  copias="$(kubectl get deployment "emparejamiento-${region}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  criterio "REG-antes-${region}" "$([ "${copias:-0}" -ge 1 ] && echo 0 || echo 1)" "emparejamiento-${region} copias listas = ${copias:-0}"
done

resultado ""
resultado "## 2. Agregar Cono Sur (reutiliza infra/pulsar/agregar-region.sh)"
kubectl delete job agregar-region-conosur --ignore-not-found >>"$SALIDA" 2>&1
kubectl create configmap pulsar-scripts-agregar-region \
  --from-file="$RAIZ/infra/pulsar/agregar-region.sh" \
  --from-file="$RAIZ/infra/pulsar/comun.sh" \
  --from-file="$RAIZ/infra/pulsar/topologia.env" \
  --dry-run=client -o yaml | kubectl apply -f - >>"$SALIDA" 2>&1
kubectl delete job agregar-region-conosur --ignore-not-found >>"$SALIDA" 2>&1
cat <<EOF | kubectl apply -f - >>"$SALIDA" 2>&1
apiVersion: batch/v1
kind: Job
metadata:
  name: agregar-region-conosur
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: agregar-region
          image: apachepulsar/pulsar:3.2.2
          command: ["bash", "/infra/agregar-region.sh", "conosur"]
          env:
            - name: PULSAR_ADMIN_URL
              value: "http://broker:8080"
          volumeMounts:
            - name: scripts
              mountPath: /infra
      volumes:
        - name: scripts
          configMap: { name: pulsar-scripts-agregar-region, defaultMode: 0755 }
EOF
kubectl wait --for=condition=complete job/agregar-region-conosur --timeout=120s >>"$SALIDA" 2>&1
exito_job="$?"
criterio CA-3.22a "$exito_job" "Job agregar-region-conosur completó"

resultado ""
resultado "## 3. Desplegar el consumidor de la región nueva"
REGISTRO="${REGISTRO:-$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${AWS_REGION:-us-east-1}.amazonaws.com}"
TAG="${HOGAR_ALPES_TAG:-$(git -C "$RAIZ" rev-parse --short HEAD)}"
sed -e "s#PLACEHOLDER_ECR#${REGISTRO}#g" -e "s#PLACEHOLDER_TAG#${TAG}#g" \
  "$RAIZ/infra/k8s/servicios/emparejamiento-conosur.yaml" | kubectl apply -f - >>"$SALIDA" 2>&1
kubectl rollout status deployment/emparejamiento-conosur --timeout=120s >>"$SALIDA" 2>&1
copias_conosur="$(kubectl get deployment emparejamiento-conosur -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
criterio CA-3.22b "$([ "${copias_conosur:-0}" -ge 1 ] && echo 0 || echo 1)" "emparejamiento-conosur copias listas = ${copias_conosur:-0}"

resultado ""
resultado "## 4. Las regiones que ya estaban activas no se interrumpieron"
for region in andina norteamerica; do
  copias="$(kubectl get deployment "emparejamiento-${region}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  criterio "REG-despues-${region}" "$([ "${copias:-0}" -ge 1 ] && echo 0 || echo 1)" "emparejamiento-${region} copias listas = ${copias:-0} (no debe haber bajado)"
done

resultado ""
resultado "## Resumen"
if [ "$fallos" -gt 0 ]; then resultado "FALLA · $fallos criterio(s) no se cumplieron · detalle en $SALIDA"; exit 1; fi
resultado "PASA · región nueva en caliente verificada en Kubernetes · detalle en $SALIDA"
