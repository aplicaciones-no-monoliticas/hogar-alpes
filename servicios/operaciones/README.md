# Operaciones

Microservicio nuevo (`01-especificacion.md` §4.2). Contexto acotado
**Operaciones y Calidad** — en HDA-003 es un **reactor**: solo consume
eventos, nunca recibe comandos. Extraído del módulo `operaciones` que vivía
dentro de `gestion_trabajos` (`docs/02-plan-tecnico.md` §8). Copiado de
`servicios/_plantilla` (`INF-6`).

## De señal en proceso a suscripción Pulsar

Es el cambio de diseño real de la entrega (G-1): antes, `operaciones` recibía
las señales `pydispatch` que la Unidad de Trabajo de `trabajos` emitía **antes**
del commit, dentro del mismo proceso y la misma transacción. Ahora es un
servicio aparte, con su propia base de datos y su propia transacción, que se
entera del mundo por una única suscripción durable a Pulsar.

## Una sola suscripción, todas las regiones

A diferencia de Emparejamiento (una réplica por región), Operaciones se
suscribe **por patrón** — `evt-trabajo-.*`, Failover, suscripción `operaciones`
— y así una sola réplica cubre todas las regiones existentes y las que se
agreguen en caliente (CA-8.4), sin redesplegar. Es la corrección de `G-2`: un
solo stream por región y `trabajo_id` como clave, así que dentro de un mismo
trabajo el orden entre `TrabajoCreado` y `EstadoTrabajoCambiado` está
garantizado.

## La capa anticorrupción (`infraestructura/consumidores.py`)

Por cada mensaje de `evt-trabajo-.*`:

1. Traduce el evento de integración a un comando **interno**: `TrabajoCreado`
   → `AbrirSeguimiento`, `EstadoTrabajoCambiado` → `RegistrarCambioEstado`.
2. El comando se ejecuta en **su propia** Unidad de Trabajo (OPS-2).
3. `ack` después del commit; `negative_acknowledge` si algo lanza una
   excepción, para que Pulsar reentregue.

## Idempotencia — `eventos_procesados` (OPS-3)

Cada `evento_id` se registra una sola vez, con su resultado:

| Resultado | Cuándo |
|---|---|
| `APLICADO` | Primera vez que se procesa el evento y hay seguimiento (o se abre uno) |
| `DUPLICADO` | El `evento_id` ya se procesó, o el `trabajo_id` ya tenía seguimiento abierto |
| `HUERFANO` | Llega un cambio de estado sin seguimiento abierto — **no se descarta en silencio** (corrige G-2, CA-6.5) |

## Endpoints

| Método | Ruta | Consulta |
|---|---|---|
| `GET` | `/seguimientos/{trabajoId}` | `ObtenerSeguimientoDeTrabajo` |
| `GET` | `/seguimientos/conteo?desde=` | `ContarSeguimientos` — instrumento de CA-6.4 |
| `GET` | `/eventos-procesados/conteo?resultado=` | `ContarEventosProcesados` — instrumento de CA-6.4 (duplicados) y CA-6.5 (huérfanos) |
| `GET` | `/health` | — |

Reemplaza a `GET /trabajos/<id>/seguimiento`, que servía GT leyendo el módulo
`operaciones` en el mismo proceso (G-6): esa llamada, tras la extracción,
habría sido GT → OPS por HTTP, prohibida por RNF-1.

## Pruebas

```bash
pip install -r requirements.txt
pytest
```

SQLite en memoria, sin broker (`tests/conftest.py` no aplica aquí porque
Operaciones no publica eventos de integración en la Entrega 4 — el
`Despachador` no se usa). La integración real contra un clúster vivo se
verifica con `escenarios/escenario-6.sh`.
