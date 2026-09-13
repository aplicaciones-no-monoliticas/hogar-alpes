# Emparejamiento

Microservicio nuevo (`01-especificacion.md` §4.3). Contexto acotado
**Emparejamiento y Publicación**. Copiado de `servicios/_plantilla` (`INF-6`).

## Una réplica por región

A diferencia de Operaciones (una sola suscripción por patrón para todas las
regiones), cada réplica de Emparejamiento atiende **una** región: se suscribe
a `evt-trabajo-{REGION}` con la suscripción `emparejamiento-{REGION}` que ya
crea `infra/pulsar/inicializar.sh` / `agregar-region.sh`. `REGION` es
obligatoria en el proceso consumidor (`config/topicos.py` falla rápido si
falta). Agregar una región nueva es desplegar una réplica nueva con su propio
`REGION`, no tocar las que ya corren (CA-8.4).

## Dos suscripciones, `ROL_CONSUMIDOR`

El proceso `consumidor` puede correr una suscripción o las dos:

| `ROL_CONSUMIDOR` | Suscripción | Para qué |
|---|---|---|
| `regional` | `evt-trabajo-{REGION}` (Failover) | EMP-3: dispara `EmparejarTrabajo` |
| `proyeccion` | `evt-acreditacion` (Failover, `emparejamiento-proyeccion`) | EMP-2: alimenta `proveedores_candidatos` |
| `todos` (por defecto) | las dos, en hilos separados | desarrollo / una sola réplica por región |

El escenario 8 escala **solo** la regional (`ROL_CONSUMIDOR=regional`,
`docker compose --scale`): así 1 → 2 → 4 réplicas miden el drenaje de
`evt-trabajo`, no arrastran réplicas ociosas de la proyección (`compose.yml`
es tarea de INT-1).

## Dos modelos de lectura, una base de datos

- **`proveedores_candidatos`** — la PROYECCIÓN, alimentada solo por
  `evt-acreditacion`. `upsert` aplica el cambio únicamente si `version` es
  mayor que la almacenada: idempotente y tolerante al desorden. La regla de
  negocio *«solo `ACREDITADA` y vigente»* vive en la consulta, no en la
  agregación de escritura.
- **`emparejamientos`** — el resultado por trabajo: candidatos identificados
  o ninguno. `EmparejarTrabajo` es idempotente ante reentrega del mismo
  `trabajo_id` (no repite la búsqueda ni republica el evento).

## Integración

- **Consume** `evt-trabajo-{región}` (solo `TrabajoCreado`; un cambio de
  estado se ignora) y `evt-acreditacion`.
- **Publica** `evt-emparejamiento`: `CandidatosIdentificados` o
  `SinCandidatos`, después del commit. Nadie lo consume en la Entrega 4 —lo
  hará la saga de la Entrega 5— pero se publica igual.

## Endpoints

| Método | Ruta | Consulta |
|---|---|---|
| `GET` | `/candidatos?categoria=&pais=&ciudad=` | `ObtenerCandidatos` |
| `GET` | `/emparejamientos/{trabajoId}` | `ObtenerEmparejamiento` |
| `GET` | `/health` | — |

## Pruebas

```bash
pip install -r requirements.txt
pytest
```

Igual que en Acreditación: SQLite en memoria, sin broker (`tests/conftest.py`
reemplaza la publicación por un no-op). La integración real se verifica con
`escenarios/escenario-8.sh` contra un clúster vivo.
