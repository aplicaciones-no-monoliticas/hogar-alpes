# Hoja de verificación — infraestructura desplegada y flujo de eventos

## Índice

- [1. La infraestructura está arriba](#1-la-infraestructura-está-arriba)
- [2. La topología de Pulsar existe como se declaró](#2-la-topología-de-pulsar-existe-como-se-declaró)
- [3. Seguir un evento de punta a punta](#3-seguir-un-evento-de-punta-a-punta)
- [4. Ver el backlog y las suscripciones en vivo](#4-ver-el-backlog-y-las-suscripciones-en-vivo)
- [5. Logs por servicio y por correlation_id](#5-logs-por-servicio-y-por-correlation_id)
- [6. Aislamiento de red y de datos (que no es solo palabra)](#6-aislamiento-de-red-y-de-datos-que-no-es-solo-palabra)
- [7. Problemas comunes en vivo](#7-problemas-comunes-en-vivo)

---

## 1. La infraestructura está arriba

```bash
# Estado de todos los contenedores — deben verse healthy o running
docker compose ps --format "table {{.Name}}\t{{.Status}}"

# Las cuatro API responden
curl -s localhost:8000/health   # gestión de trabajos
curl -s localhost:8001/health   # operaciones
curl -s localhost:8002/health   # acreditación
curl -s localhost:8003/health   # emparejamiento

# El clúster de Pulsar en sí (no solo el contenedor "running")
docker compose exec broker-1 bin/pulsar-admin brokers healthcheck
docker compose exec broker-1 bin/pulsar-admin brokers list cluster-hda
docker compose exec broker-1 bin/pulsar-admin bookies list-bookies
```

> "Ocho contenedores de servicio (API + consumidor por cada uno de los
> cuatro), ZooKeeper, dos bookies, dos brokers, y cuatro PostgreSQL — uno por
> servicio, sin compartir nada."

Si es AWS y se desplegó con Terraform:

```bash
cd infra/aws/terraform
terraform output urls        # las cuatro URL /health con la IP real
```

---

## 2. La topología de Pulsar existe como se declaró

```bash
docker compose exec broker-1 bin/pulsar-admin tenants list
docker compose exec broker-1 bin/pulsar-admin namespaces list hogar-alpes

# Tópicos por namespace (deben coincidir con infra/pulsar/README.md)
docker compose exec broker-1 bin/pulsar-admin topics list hogar-alpes/trabajos
docker compose exec broker-1 bin/pulsar-admin topics list hogar-alpes/acreditacion
docker compose exec broker-1 bin/pulsar-admin topics list hogar-alpes/emparejamiento

# Particiones y suscripciones de un tópico puntual
docker compose exec broker-1 bin/pulsar-admin topics partitioned-lookup \
  persistent://hogar-alpes/trabajos/evt-trabajo-andina
docker compose exec broker-1 bin/pulsar-admin topics subscriptions \
  persistent://hogar-alpes/trabajos/evt-trabajo-andina

# Políticas activas (TTL, cuota de backlog, compatibilidad de esquema)
docker compose exec broker-1 bin/pulsar-admin namespaces get-retention hogar-alpes/trabajos
docker compose exec broker-1 bin/pulsar-admin namespaces get-backlog-quotas hogar-alpes/trabajos
docker compose exec broker-1 bin/pulsar-admin namespaces get-schema-compatibility-strategy hogar-alpes/trabajos
```

> "Las suscripciones `operaciones` y `emparejamiento-andina` ya existen antes
> de que cualquier trabajo se cree — por eso un evento nunca se pierde
> aunque el consumidor todavía no haya arrancado."

---

## 3. Seguir un evento de punta a punta

Idea: crear un trabajo real, y mostrar el **mismo `correlation_id`**
apareciendo en la API, en el mensaje crudo del broker, y en el log del
consumidor que lo procesó — la prueba de que la comunicación es real y no un
diagrama.

```bash
# 1. Crear el trabajo — anota el id que devuelve (202 Accepted)
curl -s -X POST localhost:8000/trabajos -H 'Content-Type: application/json' -d '{
  "canal":"MARKETPLACE","partner_id":"seguros-alpes","referencia_externa":"DEMO-LOGS",
  "categoria":"PLOMERIA","urgencia":"CRITICA",
  "pais":"CO","ciudad":"Bogota","direccion":"Cra 7 # 71-21",
  "descripcion":"Seguimiento de flujo por logs"}' | tee /tmp/trabajo.json

TRABAJO_ID=$(python3 -c "import json;print(json.load(open('/tmp/trabajo.json'))['id'])")
echo "trabajo_id=$TRABAJO_ID"
```

```bash
# 2. Ver, en el log del consumidor, la misma correlación llegando y
#    procesándose (grep por el trabajo_id / correlation_id)
docker compose logs --since 2m gestion-trabajos gestion-trabajos-consumidor \
  operaciones-consumidor emparejamiento-andina | grep -F "$TRABAJO_ID"
```

```bash
# 3. Ver el mensaje crudo tal cual viaja por el broker (el correlation_id
#    en el "sobre" es el mismo trabajo_id)
for p in 0 1 2 3; do
  echo "=== partición $p ==="
  docker compose exec broker-1 bin/pulsar-admin topics stats \
    persistent://hogar-alpes/trabajos/evt-trabajo-andina-partition-$p \
    2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('msgInCounter:', d.get('msgInCounter'))"
done

docker compose exec broker-1 bin/pulsar-admin topics examine-messages persistent://hogar-alpes/trabajos/evt-trabajo-andina-partition-<N>
```

```bash
# 4. Confirmar en la proyección de Operaciones que el evento se aplicó
sleep 3
curl -s localhost:8001/seguimientos/$TRABAJO_ID | python3 -m json.tool
```

> "Gestión de Trabajos publicó y siguió — nunca llamó a Operaciones. Fue la
> propia suscripción de Operaciones la que se enteró. El `correlation_id`
> que ves en el log del consumidor es el mismo `id` que devolvió el `POST` —
> esa es la trazabilidad de un incidente distribuido (`TO-4`)."

Para el flujo de acreditación → emparejamiento, el mismo patrón — ojo: el `id`
de la acreditación NO es el `proveedor_id`. Si se omite `acreditacion_id` en
el cuerpo (como aquí), el comando genera un UUID nuevo — hay que capturar el
que devuelve el `POST`, igual que con `TRABAJO_ID` arriba:

```bash
curl -s -X POST localhost:8002/acreditaciones -H 'Content-Type: application/json' -d '{
  "proveedor_id":"prov-demo-logs","pais":"CO","ciudad":"Bogota",
  "categorias":["PLOMERIA"],"nivel":"ORO","vigencia_meses":12}' | tee /tmp/acreditacion.json

ACREDITACION_ID=$(python3 -c "import json;print(json.load(open('/tmp/acreditacion.json'))['id'])")
echo "acreditacion_id=$ACREDITACION_ID"

curl -s -X PUT "localhost:8002/acreditaciones/$ACREDITACION_ID/aprobar" -H 'Content-Type: application/json' -d '{}'

docker compose logs --since 1m acreditacion-consumidor emparejamiento-proyeccion \
  | grep -E "$ACREDITACION_ID|prov-demo-logs"
# el comando SOLICITAR/APROBAR viaja con acreditacion_id; el evento
# evt-acreditacion que recibe emparejamiento-proyeccion (capa anticorrupción,
# EMP-2) va por proveedor_id, no por acreditacion_id — por eso el grep busca
# los dos.

curl -s "localhost:8003/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota" | python3 -m json.tool
```

---

## 4. Ver el backlog y las suscripciones en vivo

Útil para mostrar, sin correr el escenario formal, que un consumidor caído
**acumula** en su propia suscripción sin afectar a las demás:

```bash
# Backlog por suscripción, tópico particionado completo (las 4 particiones)
docker compose exec broker-1 bin/pulsar-admin topics partitioned-stats \
  persistent://hogar-alpes/trabajos/evt-trabajo-andina | python3 -m json.tool

# Solo el número de mensajes pendientes por suscripción (más legible)
docker compose exec broker-1 bin/pulsar-admin topics partitioned-stats \
  persistent://hogar-alpes/trabajos/evt-trabajo-andina \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    [print(s, v['msgBacklog']) for s,v in d['subscriptions'].items()]"
```

```bash
# Simular la caída: detener el consumidor de Operaciones, generar tráfico,
# ver crecer SOLO su backlog
docker compose stop operaciones-consumidor
python3 herramientas/generador_carga.py --via-http http://localhost:8000 --total 20 --tasa 5
# repetir el comando de partitioned-stats de arriba: "operaciones" crece,
# "emparejamiento-andina" se mantiene en cero

docker compose start operaciones-consumidor
# repetir de nuevo: "operaciones" vuelve a cero — drenó todo
```

Panel visual opcional (Pulsar Manager, detrás de un profile de Compose — ver
`infra/pulsar/README.md` para el aviso sobre su bug de login conocido):

```bash
docker compose --profile demo up -d pulsar-manager
infra/pulsar/pulsar-manager-setup.sh   # una sola vez
# http://localhost:9527 (o el puerto publicado en AWS)
```

---

## 5. Logs por servicio y por correlation_id

```bash
# Logs en vivo de un servicio (API + consumidor)
docker compose logs -f gestion-trabajos gestion-trabajos-consumidor

# Logs en vivo de TODOS los consumidores (para ver el flujo completo pasar)
docker compose logs -f gestion-trabajos-consumidor operaciones-consumidor \
  acreditacion-consumidor emparejamiento-proyeccion emparejamiento-andina

# Buscar todo lo relacionado con un trabajo/proveedor puntual, en todo el sistema
docker compose logs --since 10m | grep -F "$TRABAJO_ID"

# Solo errores o reintentos (el consumidor loguea con logger.exception si falla)
docker compose logs --since 30m | grep -iE "error|exception|reentregará"
```

> Los logs son texto plano con `logging.basicConfig` (no JSON estructurado):
> `grep` por el `trabajo_id`/`correlation_id` es la forma confiable de
> correlacionar entre servicios, no buscar por timestamp.

---

## 6. Aislamiento de red y de datos (que no es solo palabra)

```bash
# Gestión de Trabajos ni siquiera puede RESOLVER la base de Acreditación
docker compose exec gestion-trabajos getent hosts postgres-acreditacion   # falla, a propósito

# Cada servicio solo ve su propia base de datos
docker compose exec gestion-trabajos getent hosts postgres-trabajos       # sí resuelve

# Ningún servicio de aplicación puede llamar directo a otra API por HTTP
# interno — todo pasa por el broker, nunca por red de aplicación a aplicación
docker compose exec gestion-trabajos python3 -c "import urllib.request; urllib.request.urlopen('http://operaciones:5000/health', timeout=2)"  # falla: no comparten red
```

---

## 7. Problemas comunes en vivo

```bash
# El sistema quedó en un estado raro (consumidor detenido a medias, etc.)
docker compose up -d

# Reconstruir un servicio puntual tras un cambio de código
docker compose up -d --build gestion-trabajos gestion-trabajos-consumidor

# Ver qué versión de la topología de Pulsar quedó aplicada (re-corre, es idempotente)
docker compose run --rm pulsar-config

# Si un escenario dejó réplicas de más (post escenario 8)
docker compose up -d --scale emparejamiento-andina=1 --scale gestion-trabajos-consumidor=1
```
