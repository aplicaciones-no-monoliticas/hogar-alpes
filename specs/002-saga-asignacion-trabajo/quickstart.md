# Quickstart: validar la saga de asignación

## Prerrequisitos

- `docker compose up -d --build` desde un clon limpio (levanta Pulsar, los cinco servicios de la
  Entrega 4 y el nuevo `saga-log`).
- `infra/pulsar/inicializar.sh` corrido (lo hace `pulsar-config` automáticamente al levantar) con
  las suscripciones nuevas de `research.md` D6 ya creadas.
- Al menos un proveedor `ACREDITADA` y vigente cargado (usar `herramientas/cargar_acreditaciones.py`
  o el `POST /acreditaciones` + `PUT /aprobar` del BFF).

## Caso 1 — Camino feliz (CA-1.1, CA-1.2)

```bash
curl -s -X POST http://localhost:8090/trabajos/asignacion \
  -H 'Content-Type: application/json' \
  -d '{"categoria": "PLOMERIA", "urgencia": "NORMAL", "pais": "CO", "ciudad": "Bogota",
       "direccion": "Calle 1", "descripcion": "fuga", "partner_id": "demo"}'
```

Resultado esperado: `202` con `seguimiento_saga: /sagas/{id}`. Tras unos segundos:

```bash
curl -s http://localhost:8090/trabajos/{id} | jq '.estado, .proveedor_id'
# "ASIGNADO", "<algún proveedor_id>"
curl -s http://localhost:8090/sagas/{id} | jq '.estado, .pasos | length'
# "COMPLETADA", 4
```

## Caso 2 — `VIGENCIA` (CA-1.3)

Mismo `POST`, agregando `"simular_fallo": "VIGENCIA"`. Esperado: trabajo `CANCELADO`, sin
`proveedor_id`; `GET /sagas/{id}` en `COMPENSADA` con los pasos de ida (creado, propuesto,
rechazado) y de vuelta (liberados, cancelado) en orden inverso al de ida; el proveedor propuesto
vuelve a aparecer en `GET /candidatos` para un trabajo compatible nuevo (CA-1.6).

## Caso 3 — `SIN_CANDIDATOS` (CA-1.4)

Mismo `POST` con `"simular_fallo": "SIN_CANDIDATOS"`, o sencillamente una categoría/región sin
proveedores acreditados. Esperado: trabajo `CANCELADO` directo, sin que se haya reservado nadie
(sin fila en `reservas_proveedor`), `GET /sagas/{id}` en `COMPENSADA` con solo 2 pasos (creado,
cancelado).

## Caso 4 — `ASIGNACION` (CA-1.5)

Mismo `POST` con `"simular_fallo": "ASIGNACION"`. Esperado: trabajo `CANCELADO`, proveedor
liberado, `GET /sagas/{id}` en `COMPENSADA` con los cuatro pasos de ida hasta `vigencia-confirmada`
más las reversiones.

## Automatizado

`escenarios/saga.sh` corre los cuatro casos uno tras otro, imprime `PASA`/`FALLA` por cada CA-1.*
releyendo del broker/DB lo que produjo (no comparando contra sí mismo, Principio VI), guarda el
reporte en `docs/resultados/saga-<fecha>.md` y termina en menos de 5 minutos (CA-1.21, CA-1.22).

```bash
bash escenarios/saga.sh
```

## Regresión (CA-1.17 a CA-1.20)

```bash
pytest servicios/gestion_trabajos servicios/emparejamiento servicios/acreditacion servicios/saga_log
newman run postman/hogar-alpes-bff.postman_collection.json -e postman/bff-local.postman_environment.json --env-var sagasDisponibles=true
bash escenarios/escenario-6.sh   # disponibilidad, sin cambios de resultado
bash escenarios/escenario-8.sh   # escalabilidad, sin cambios de resultado
bash escenarios/mod-1.sh escenarios/mod-2.sh escenarios/mod-3.sh
```

## Verificar que `saga_log` no publica nada (CA-1.16)

```bash
grep -rn "create_producer\|publicar_evento" servicios/saga_log/src/  # sin resultados
```
