# Quickstart — validar el BFF y la trazabilidad

**Feature**: `001-bff-entry-point` · Guía de **validación**, no de implementación. Los detalles de diseño están en [contracts/](contracts/) y [data-model.md](data-model.md).

> **Estado**: escrita durante la planificación; los comandos marcados *(por confirmar)* se ajustan al implementar. Nada de lo de abajo se ha ejecutado todavía contra el BFF, porque aún no existe. Lo que se ejecutó en la planificación fue el experimento de redes de `research.md` R7.

## 0. Prerrequisitos

- Docker en marcha; clon limpio con `.env` copiado de `.env.example` (`PUERTO_BFF=8090`).
- Python 3.11 y `pip install -r servicios/<svc>/requirements.txt` para correr `pytest` por servicio.
- `newman` (`npm i -g newman`) o `npx --yes newman`, como en `escenarios/mod-1.sh`.

## 1. Pruebas automáticas (sin Docker)

```bash
# BFF (usa servidores HTTP falsos en puertos efímeros; no necesita los servicios reales)
cd servicios/bff && python -m pytest

# Los cinco servicios tocados: módulo de correlación, gancho HTTP, publicación, y regresión
for s in gestion_trabajos operaciones acreditacion emparejamiento; do (cd servicios/$s && python -m pytest); done

# Comprobaciones estáticas: sin cliente HTTP ni variables entre servicios; sin `correlation` en
# dominio/tablas; BFF sin BD/Pulsar/volúmenes; 6 copias idénticas de correlacion.py
python herramientas/verificar_aislamiento.py

# Los contratos no deben haber cambiado de forma
python herramientas/verificar_contratos.py        # necesita el broker (ver su cabecera)
```

**Esperado**: todo en verde; `verificar_aislamiento.py` imprime PASA por criterio (CA-2.3, 2.13, 2.21, copias idénticas).

## 2. Levantar el sistema desde cero

```bash
docker compose down -v && docker compose up -d --build
curl -s http://localhost:8090/health        # {"status":"up","service":"bff"}
```

**Esperado**: el BFF responde sin configuración manual (CA-2.1) y arranca aunque algún servicio de atrás no esté listo (sin `depends_on`).

## 3. Sin comunicación síncrona entre servicios (CA-2.12, CA-2.13)

La regla es que los servicios de dominio **no se llaman por HTTP** y solo se comunican por eventos de Pulsar; que compartan red no importa. Por eso la comprobación es sobre el código y la configuración, no sobre la resolución de nombres:

```bash
python herramientas/verificar_aislamiento.py     # (por confirmar) PASA/FALLA por criterio; lee docker compose config
```

Debe dar PASA en:

- Ningún servicio de dominio contiene cliente HTTP (`urllib`, `requests`, `httpx`, `http.client`, `aiohttp`) ni literales `http://` (línea base hoy: 0).
- Ninguna variable de entorno de un servicio de dominio apunta a otro servicio de dominio ni al BFF; solo el BFF tiene variables `URL_*`.
- Cada red `red-bff-*` tiene exactamente dos miembros: el BFF y un servicio de dominio.
- El BFF no declara volúmenes, `DATABASE_URI` ni `BROKER_HOST`, y no depende de `pulsar-client`, `SQLAlchemy` ni `psycopg2` (CA-2.3).

Comprobación complementaria (opcional): el BFF no está en la red del broker ni en la de las bases, así que no resuelve esos nombres.

```bash
docker compose exec bff getent hosts broker-1            # esperado: sin salida, código != 0
docker compose exec bff getent hosts postgres-trabajos   # esperado: sin salida, código != 0
```

> La comprobación de red de la Entrega 4 (`getent hosts postgres-<ajena>`, 9 de 9) sigue vigente y solo aplica a las **bases de datos**. Entre servicios de dominio **no** se espera que el nombre deje de resolver.

## 4. Reenvío fiel (US1)

```bash
BFF=http://localhost:8090

# 202 igual que directo (y con correlation_id aditivo en el cuerpo)
curl -si -X POST $BFF/trabajos -H 'Content-Type: application/json' \
  -d '{"categoria":"PLOMERIA","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","urgencia":"NORMAL"}'

# 400 de regla regional, idéntico al del servicio
curl -si -X POST $BFF/trabajos -H 'Content-Type: application/json' \
  -d '{"categoria":"SINIESTRO_GRANIZO","pais":"MX","ciudad":"CDMX","direccion":"x","urgencia":"NORMAL"}'

# 404 del servicio vs 404 propio del BFF
curl -si $BFF/trabajos/00000000-0000-0000-0000-000000000000     # del servicio
curl -si $BFF/no-existe                                          # del BFF, con grupos_disponibles
```

**Regresión contra la colección de la Entrega 4** (CA-2.6, todas las carpetas salvo la del `/health`, ver `research.md` H4):

```bash
newman run postman/hogar-alpes.postman_collection.json -e postman/bff-local.postman_environment.json \
  --folder "Escenario 7 · Escalabilidad — absorber el pico sin rechazar" \
  --folder "Eventos de integración entre servicios" \
  --folder "Escenario 3 · Modificabilidad — ciclo de vida del Trabajo" \
  --folder "Escenario 2 · Modificabilidad — reglas regionales por sidecar" \
  --folder "Validaciones del dominio"
```

## 5. Compuestos y degradación (US2)

```bash
ID=<id devuelto por POST /trabajos>
curl -s $BFF/trabajos/$ID/completo | python -m json.tool     # 4 partes, todas DISPONIBLE tras unos segundos
curl -s $BFF/estado-del-sistema     | python -m json.tool     # 6 componentes (saga-log DOWN hasta US-01)

# Degradación: detener Operaciones y repetir
docker compose stop operaciones operaciones-consumidor
curl -si $BFF/trabajos/$ID/completo        # 200; seguimiento = NO_DISPONIBLE; el resto, no
curl -si $BFF/seguimientos/$ID             # 503 que nombra "operaciones"
curl -si $BFF/candidatos?categoria=PLOMERIA\&pais=CO\&ciudad=Bogota   # sigue en 200
docker compose start operaciones operaciones-consumidor
```

**Esperado** (CA-2.8/2.9/2.10/2.14): las partes disponibles llegan; la caída de un servicio no afecta las rutas de los demás; nunca hay traza ni `500` sin explicación. Tiempo del compuesto < 2 s (`python herramientas/medir_latencia.py "$BFF/trabajos/$ID/completo" --umbral-p95-ms 2000`).

## 6. Trazabilidad: una búsqueda, toda la cadena (US3)

```bash
CID=$(curl -s -X POST $BFF/trabajos -H 'Content-Type: application/json' \
  -d '{"categoria":"PLOMERIA","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","urgencia":"NORMAL"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['correlation_id'])")

sleep 5
docker compose logs --no-color -t | grep -F "$CID" | sort -t'|' -k2
```

**Esperado** (CA-2.17c, CA-2.18): líneas con `cid=$CID` del BFF, Gestión de Trabajos (API y consumidor), Operaciones y Emparejamiento, en orden de tiempo. Con US-01 en marcha, también Acreditación y `saga-log` (*pendiente hasta entonces*).

**Cabecera en toda respuesta** (CA-2.17): comprobar `X-Correlation-Id` en un `202`, un `400`, un `404` del servicio, un `404` propio y un `503`:

```bash
curl -si $BFF/trabajos/00000000-0000-0000-0000-000000000000 | grep -i x-correlation-id
curl -si -H 'X-Correlation-Id: mi-id-de-prueba' $BFF/health | grep -i x-correlation-id   # respeta el del cliente
curl -si -H 'X-Correlation-Id: con espacios y | raros' $BFF/health | grep -i x-correlation-id # inválido: lo reemplaza
```

**En el broker** (CA-2.19, *por confirmar*): consumir con una suscripción temporal y ver `properties` y el sobre.

```bash
docker compose exec broker-1 bin/pulsar-client consume \
  persistent://hogar-alpes/trabajos/evt-trabajo-andina -s verif-cid -n 5 -p Earliest
# esperado: properties incluye correlation_id=$CID y el sobre lleva el mismo valor
docker compose exec broker-1 bin/pulsar-admin topics unsubscribe persistent://hogar-alpes/trabajos/evt-trabajo-andina -s verif-cid
```

**Clave de partición intacta** (CA-2.20): prueba unitaria (`partition_key == '<trabajo_id>'`) y `bash escenarios/escenario-8.sh` sin modificaciones.

**Sin pasar por el BFF** (CA-2.22): llamar directo a un servicio (`curl -i localhost:8000/trabajos …`) y comprobar que el `X-Correlation-Id` devuelto existe y aparece en sus logs; `escenarios/bff.sh` también publica un mensaje con el campo vacío.

## 7. Colección completa del BFF (US4)

```bash
newman run postman/hogar-alpes-bff.postman_collection.json -e postman/bff-local.postman_environment.json
bash escenarios/bff.sh        # además: servicio detenido, cadena de logs, mensaje sin id; PASA/FALLA en docs/resultados/
```

**Esperado**: verde, sin intervención manual (CA-2.25). Las carpetas `5 · Sagas` y `7 · Saga de punta a punta` quedan **pendientes** hasta que exista `saga_log` (US-01); se reportan como *pendiente*, no como PASA.

## 8. Regresión de los escenarios de la Entrega 4

Como el cambio de correlación toca la publicación y el consumo de todos los servicios (Constitución, puertas de calidad; la topología de red no cambia), ejecutar y comparar con los resultados previos:

```bash
bash escenarios/escenario-6.sh && bash escenarios/escenario-8.sh
bash escenarios/mod-1.sh && bash escenarios/mod-2.sh && bash escenarios/mod-3.sh
python escenarios/esquemas.py
```

Los resultados quedan en `docs/resultados/` (no se versiona). Lo que no se pueda ejecutar se anota como **pendiente**.
