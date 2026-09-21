# Configuración del clúster

- `reglas_regionales.json` — **copia** de `infra/sidecar/reglas_regionales.json` (FR-017). Es la
  que Kubernetes convierte en `ConfigMap` (ver `kustomization.yaml` en
  `infra/k8s/entornos/base/`) y monta en `gestion-trabajos`/`gestion-trabajos-consumidor`, igual
  que Compose monta el archivo original como volumen. **Agregar un país** en Kubernetes es editar
  este archivo y correr `kubectl apply -k infra/k8s/entornos/<entorno>/` seguido de
  `kubectl rollout restart deployment/gestion-trabajos-api deployment/gestion-trabajos-consumidor`
  — 0 archivos de código, 0 imágenes reconstruidas (CA-3.23). Compose sigue leyendo su propio
  archivo en `infra/sidecar/`; los dos no se sincronizan automáticamente entre sí — un cambio
  regional pensado para ambos entornos se aplica a mano en los dos archivos.
- `variables-comunes.env` — variables no secretas compartidas por los servicios (host/puerto de
  Pulsar, nombres de tópicos, nivel de log), equivalentes a las que hoy están sueltas como
  variables de entorno en `docker-compose.yml`.
