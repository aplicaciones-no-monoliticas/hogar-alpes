# Pulsar en Kubernetes

`zookeeper.yaml` → `job-cluster-init.yaml` → `bookies.yaml` → `brokers.yaml` →
`job-topology-init.yaml`, en ese orden (ver `infra/k8s/desplegar.sh`).

El `ConfigMap` `pulsar-scripts` que monta `job-topology-init.yaml` **no está en este
directorio**: `desplegar.sh` lo genera en el momento del despliegue directamente desde
`infra/pulsar/{inicializar.sh,comun.sh,topologia.env}` con
`kubectl create configmap pulsar-scripts --from-file=infra/pulsar/inicializar.sh --from-file=infra/pulsar/comun.sh --from-file=infra/pulsar/topologia.env`.
Así el guion que corre dentro del clúster es siempre exactamente el mismo archivo versionado en
`infra/pulsar/` — nunca una copia que se puede desincronizar (constitución: "no hay que
reescribirlo").
