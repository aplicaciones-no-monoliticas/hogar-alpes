# Data Model — BFF y trazabilidad por petición

**Feature**: `001-bff-entry-point`

**El BFF no persiste nada.** No hay tablas, migraciones ni almacenamiento (FR-007, FR-008). Todo lo de abajo son estructuras **en memoria y de vida corta** —una por petición— y el contexto del identificador de correlación en los servicios existentes. En los servicios **no** se agrega ninguna entidad de dominio, columna ni tabla (FR-030, CA-2.21).

---

## 1. Servicio de destino (configuración, no dato)

| Campo | Tipo | Origen | Regla |
|---|---|---|---|
| `nombre` | texto | constante | Uno de `gestion-trabajos`, `operaciones`, `acreditacion`, `emparejamiento`, `saga-log`. Es el que aparece en los mensajes `503`/`502` |
| `url_base` | texto | variable de entorno `URL_*` | Valor por defecto `http://<nombre>:5000` |
| `grupo` | texto | constante | `Trabajos` · `Seguimiento` · `Acreditaciones` · `Emparejamiento` · `Sagas` |

Cada grupo de rutas se asocia a **exactamente un** servicio.

| Grupo | Servicio | Variable |
|---|---|---|
| Trabajos | `gestion-trabajos` | `URL_TRABAJOS` |
| Seguimiento | `operaciones` | `URL_OPERACIONES` |
| Acreditaciones | `acreditacion` | `URL_ACREDITACION` |
| Emparejamiento | `emparejamiento` | `URL_EMPAREJAMIENTO` |
| Sagas | `saga-log` | `URL_SAGAS` |

## 2. Ruta de reenvío (dato, `rutas.py`)

| Campo | Tipo | Regla |
|---|---|---|
| `metodo` | `GET` \| `POST` \| `PUT` | Debe coincidir con el del servicio |
| `patron` | texto | Ruta al estilo Flask (`/trabajos/<id>/estado`); la misma en el BFF y en el servicio |
| `servicio` | referencia a §1 | Obligatorio |

Son 17 (tabla en `contracts/bff-api.md`). **Invariante** (lo prueba un test): el conjunto de rutas de la tabla es igual al de los blueprints de los servicios, salvo `/health`.

## 3. Petición entrante (por petición, en memoria)

| Campo | Tipo | Regla |
|---|---|---|
| `metodo`, `ruta`, `consulta` | texto | Se reenvían sin modificar |
| `cuerpo` | bytes, opcional | Se reenvía sin modificar |
| `correlation_id` | texto | Ver §4; **siempre** presente al terminar el gancho de entrada |

## 4. Identificador de correlación (contexto de borde)

| Aspecto | Definición |
|---|---|
| Almacén | `ContextVar` del módulo `correlacion.py` (uno por hilo/petición; nunca compartido entre peticiones) |
| Forma válida | `^[A-Za-z0-9._:-]{1,64}$` |
| Valor generado | `str(uuid.uuid4())` (36 caracteres, cumple la forma válida) |
| Ciclo de vida | Se **fija** al entrar (petición HTTP o mensaje consumido) → se **lee** al publicar y al escribir cada línea de registro → se **restaura** al salir |
| ¿Dónde vive? | Cabecera HTTP, campo `correlation_id` del sobre del mensaje, propiedad `correlation_id` del mensaje, línea de registro. **En ningún otro lugar** |
| ¿Dónde NO vive? | Comandos, eventos de dominio, entidades, objetos valor, tablas. Es información de transporte (FR-030) |
| Relación con la clave de partición | **Ninguna.** La clave sigue siendo `trabajo_id` (`proveedor_id` en Acreditación) y viaja como argumento `partition_key`; el identificador viaja en el sobre y en las propiedades, que Pulsar no usa para enrutar (FR-031) |

**Transiciones del valor efectivo** (`normalizar` → `actual`):

| Entrada | Resultado |
|---|---|
| Cabecera/campo/propiedad con forma válida | Se respeta tal cual |
| Ausente, vacío, `None` | Se crea uno nuevo |
| Demasiado largo (> 64) o con caracteres fuera de `A-Za-z0-9._:-` | Se trata como ausente: se crea uno nuevo |
| Sin contexto al publicar (p. ej. un script) | `actual()` crea uno y lo deja fijado, de modo que sobre y propiedades **coinciden** |

## 5. Respuesta del servicio de atrás (en memoria)

| Campo | Tipo | Regla |
|---|---|---|
| `codigo` | entero | |
| `cuerpo` | bytes | |
| `tipo_contenido` | texto | |
| — o — `fallo` | enumeración | `TIMEOUT` · `CONEXION_RECHAZADA` · `DNS` · `ERROR_INTERNO_UPSTREAM` (5xx) |

## 6. Parte de una respuesta compuesta (en memoria)

| Campo | Tipo | Regla |
|---|---|---|
| `estado` | enumeración | `DISPONIBLE` · `TODAVIA_NO_DISPONIBLE` · `NO_DISPONIBLE` |
| `datos` | objeto | Solo con `DISPONIBLE`; es el cuerpo **sin modificar** del servicio |
| `servicio` | texto | Solo con `NO_DISPONIBLE` |
| `motivo` | enumeración | Solo con `NO_DISPONIBLE`: `TIMEOUT` · `CONEXION_RECHAZADA` · `DNS` · `ERROR_INTERNO_UPSTREAM` · `RESPUESTA_INESPERADA` · `DEPENDE_DE_ACREDITACION` |

**Clasificación de una llamada a una parte:**

| Resultado de la llamada | ¿Parte raíz? | Estado de la parte | Efecto sobre la respuesta |
|---|---|---|---|
| `200` | — | `DISPONIBLE` | — |
| `404` | **Sí** (`trabajo`, `acreditacion`) | — | **Toda** la respuesta es ese `404` sin modificar |
| `404` | No (seguimiento, emparejamiento, saga) | `TODAVIA_NO_DISPONIBLE` | — |
| Fallo de conexión / DNS / tiempo límite | Cualquiera | `NO_DISPONIBLE` | — |
| `5xx` | Cualquiera | `NO_DISPONIBLE` (`ERROR_INTERNO_UPSTREAM`) | — |
| Otro `4xx` (no esperado en estas consultas `GET`) | Cualquiera | `NO_DISPONIBLE` con motivo `RESPUESTA_INESPERADA`; se registra | — |

**Regla global:** si **todas** las partes son `NO_DISPONIBLE` → `503`; si no → `200`. Excepción deliberada: `GET /estado-del-sistema` siempre responde `200` (ver `research.md` R5).

## 7. Componente de sistema (solo en `/estado-del-sistema`)

| Campo | Tipo | Regla |
|---|---|---|
| `estado` | enumeración | `UP` (el `/health` respondió `200`) · `DOWN` |
| `latencia_ms` | entero | Solo con `UP` |
| `motivo` | enumeración | Solo con `DOWN` (mismos valores que §6) |

Son seis: el propio `bff` (siempre `UP` si responde) y los cinco servicios. `estado_general` = `OK` si los seis están `UP`; `DEGRADADO` en cualquier otro caso.

## 8. Error propio del BFF (por respuesta)

| Campo | Tipo | Presente en |
|---|---|---|
| `error` | texto legible | Siempre |
| `correlation_id` | texto | Siempre |
| `servicio` | texto | `503`, `502` |
| `motivo` | enumeración | `503` |
| `status_upstream` | entero | `502` |
| `grupos_disponibles` | lista de `{grupo, rutas[]}` | `404` de ruta desconocida |
| `metodos_permitidos` | lista | `405` |

Nunca contiene trazas, rutas de archivo ni texto crudo de un servicio.
