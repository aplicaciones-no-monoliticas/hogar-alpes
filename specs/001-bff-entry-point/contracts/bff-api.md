# Contrato — API del BFF

**Feature**: `001-bff-entry-point` · **Base local**: `http://localhost:8090` (`PUERTO_BFF`) · **Formato**: JSON, UTF-8

Este contrato describe **solo lo que el BFF define**. El contrato de cada ruta de reenvío es el del servicio de atrás (no se repite aquí); la regla es que el BFF lo devuelve sin cambios, con las dos salvedades de §2.

## 1. Cabeceras comunes

| Cabecera | Sentido | Regla |
|---|---|---|
| `X-Correlation-Id` | Petición → BFF | Opcional. Si es válida (`^[A-Za-z0-9._:-]{1,64}$`) se respeta; si falta o es inválida, el BFF crea una |
| `X-Correlation-Id` | BFF → servicio | Siempre; es el identificador vigente |
| `X-Correlation-Id` | BFF → cliente | **En toda respuesta, sin excepción**: `2xx`, `4xx` de negocio, `404`/`405` propios, `502`, `503`, `500` |

## 2. Rutas de reenvío (17) — misma ruta, mismo cuerpo, mismo código

| Grupo | Método y ruta | Servicio | Variable |
|---|---|---|---|
| Trabajos | `POST /trabajos` | `gestion-trabajos` | `URL_TRABAJOS` |
| Trabajos | `GET /trabajos/{id}` | `gestion-trabajos` | |
| Trabajos | `GET /trabajos?estado=` | `gestion-trabajos` | |
| Trabajos | `PUT /trabajos/{id}/estado` | `gestion-trabajos` | |
| Seguimiento | `GET /seguimientos/{id}` | `operaciones` | `URL_OPERACIONES` |
| Seguimiento | `GET /seguimientos/conteo` | `operaciones` | |
| Seguimiento | `GET /eventos-procesados/conteo` | `operaciones` | |
| Acreditaciones | `POST /acreditaciones` | `acreditacion` | `URL_ACREDITACION` |
| Acreditaciones | `PUT /acreditaciones/{id}/aprobar` | `acreditacion` | |
| Acreditaciones | `PUT /acreditaciones/{id}/revocar` | `acreditacion` | |
| Acreditaciones | `GET /acreditaciones/{id}` | `acreditacion` | |
| Acreditaciones | `GET /acreditaciones/{id}/eventos` | `acreditacion` | |
| Emparejamiento | `GET /candidatos?categoria=&pais=&ciudad=` | `emparejamiento` | `URL_EMPAREJAMIENTO` |
| Emparejamiento | `GET /emparejamientos/{id}` | `emparejamiento` | |
| Sagas | `GET /sagas/{id}` | `saga-log` | `URL_SAGAS` |
| Sagas | `GET /sagas?estado=` | `saga-log` | |
| Sagas | `GET /sagas/resumen` | `saga-log` | |

**Reglas de reenvío:** la cadena de consulta, el cuerpo y `Content-Type`/`Accept` se envían sin modificar; código, cuerpo y `Content-Type` del servicio se devuelven sin modificar (los `400`, `404` y `409` de negocio incluidos).

**Salvedad A — campo aditivo.** En `POST /trabajos` (y `POST /trabajos/asignacion`), cuando el servicio responde `202` con un objeto JSON, el BFF **agrega** `correlation_id`:

```json
// servicio:  {"id": "b3f1…", "estado": "CREADO"}
// BFF:       {"id": "b3f1…", "estado": "CREADO", "correlation_id": "5d0c…"}
```

**Salvedad B — `/health`.** `GET /health` es el del **propio BFF** (`{"status":"up","service":"bff"}`), no se reenvía.

**Fallos del servicio de atrás:**

| Situación | Código | Cuerpo |
|---|---|---|
| No resuelve / rechaza / agota tiempo | `503` | `{"error":"Servicio no disponible: operaciones","servicio":"operaciones","motivo":"TIMEOUT","correlation_id":"…"}` |
| El servicio responde `5xx` | `502` | `{"error":"El servicio operaciones respondió con un error interno","servicio":"operaciones","status_upstream":500,"correlation_id":"…"}` |

## 3. Errores propios del BFF

| Situación | Código | Cuerpo |
|---|---|---|
| Ruta no existe en ningún servicio | `404` | `{"error":"Ruta no encontrada","grupos_disponibles":[{"grupo":"Trabajos","rutas":["POST /trabajos","GET /trabajos/{id}", …]}, …],"correlation_id":"…"}` |
| Ruta existe con otro método | `405` | `{"error":"Método no permitido","metodos_permitidos":["GET"],"correlation_id":"…"}` |
| Error no previsto en el BFF | `500` | `{"error":"Error interno del BFF","correlation_id":"…"}` — sin traza |

## 4. Endpoints compuestos (4)

Todas las partes de un compuesto llevan `{"estado": …}` con uno de `DISPONIBLE` (con `datos`), `TODAVIA_NO_DISPONIBLE` o `NO_DISPONIBLE` (con `servicio` y `motivo`). Reglas de código: ver `data-model.md` §6.

### 4.1 `GET /trabajos/{id}/completo`

Llamadas en paralelo: `GET /trabajos/{id}`, `GET /seguimientos/{id}`, `GET /emparejamientos/{id}`, `GET /sagas/{id}`. Raíz: `trabajo`.

```json
// 200 — Operaciones caído, el resto bien
{
  "trabajo_id": "b3f1…",
  "correlation_id": "5d0c…",
  "partes": {
    "trabajo":        {"estado": "DISPONIBLE", "datos": {"id": "b3f1…", "estado": "CREADO", "…": "…"}},
    "seguimiento":    {"estado": "NO_DISPONIBLE", "servicio": "operaciones", "motivo": "CONEXION_RECHAZADA"},
    "emparejamiento": {"estado": "DISPONIBLE", "datos": {"…": "…"}},
    "saga":           {"estado": "DISPONIBLE", "datos": {"…": "…"}}
  }
}
```

| Caso | Resultado |
|---|---|
| El trabajo no existe (`404` del servicio) | `404` tal cual, sin `partes` |
| Trabajo recién creado | `200`, `seguimiento`/`emparejamiento`/`saga` = `TODAVIA_NO_DISPONIBLE` |
| Todos los servicios caídos | `503` (`servicio`: lista de los nombres) |

### 4.2 `GET /proveedores/{id}/completo`

`{id}` es el **id de la acreditación** (el que devuelve `POST /acreditaciones`; ver `research.md` H3). Fase 1 en paralelo: `GET /acreditaciones/{id}` y `GET /acreditaciones/{id}/eventos`. Fase 2 en paralelo: `GET /candidatos?categoria=<c>&pais=&ciudad=` por cada categoría de la acreditación. Raíz: `acreditacion`.

```json
{
  "acreditacion_id": "9a2e…",
  "proveedor_id": "c41d…",
  "correlation_id": "5d0c…",
  "partes": {
    "acreditacion": {"estado": "DISPONIBLE", "datos": {"id": "9a2e…", "proveedor_id": "c41d…", "estado": "ACREDITADA", "…": "…"}},
    "historial":    {"estado": "DISPONIBLE", "datos": [ {"…": "…"} ]},
    "candidato":    {"estado": "DISPONIBLE", "datos": {"aparece": true, "categorias": [{"categoria": "PLOMERIA", "aparece": true, "nivel": "SENIOR"}]}}
  }
}
```

`candidato.datos.aparece` = el `proveedor_id` figura en `/candidatos` de **alguna** categoría. Si la acreditación no está disponible → `candidato` = `NO_DISPONIBLE` con `motivo: "DEPENDE_DE_ACREDITACION"`. Acreditación inexistente → `404` tal cual.

### 4.3 `GET /estado-del-sistema`

Llamadas en paralelo: `GET /health` de los cinco servicios y `GET /sagas/resumen`. **Siempre `200`.**

```json
{
  "correlation_id": "5d0c…",
  "estado_general": "DEGRADADO",
  "componentes": {
    "bff":              {"estado": "UP"},
    "gestion-trabajos": {"estado": "UP", "latencia_ms": 9},
    "operaciones":      {"estado": "UP", "latencia_ms": 7},
    "acreditacion":     {"estado": "UP", "latencia_ms": 8},
    "emparejamiento":   {"estado": "UP", "latencia_ms": 8},
    "saga-log":         {"estado": "DOWN", "motivo": "DNS"}
  },
  "sagas": {"estado": "NO_DISPONIBLE", "servicio": "saga-log", "motivo": "DNS"}
}
```

### 4.4 `POST /trabajos/asignacion`

Mismo cuerpo de entrada que `POST /trabajos`. Se reenvía a `POST /trabajos`; si el servicio responde `202`:

```json
{
  "id": "b3f1…",
  "estado": "CREADO",
  "correlation_id": "5d0c…",
  "seguimiento_saga": "/sagas/b3f1…",
  "seguimiento_completo": "/trabajos/b3f1…/completo"
}
```

Cualquier otra respuesta (`400`, `503`, …) se comporta como en el reenvío. **No** crea nada distinto de lo que crea `POST /trabajos`.

## 5. Lo que este contrato NO incluye

Autenticación, límites de tasa, caché, paginación propia, GraphQL. El BFF no valida ni transforma datos de dominio.
