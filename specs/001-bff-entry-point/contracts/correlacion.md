# Contrato — Identificador de correlación

**Feature**: `001-bff-entry-point` · Aplica al BFF **y** a los cinco servicios existentes (plantilla, Gestión de Trabajos, Operaciones, Acreditación, Emparejamiento) y a los que nazcan de la plantilla (p. ej. `saga_log`).

**Regla en una línea:** una petición recibe un código único una sola vez, al entrar; todos lo copian tal cual en cada mensaje que publican y en cada línea de registro que escriben, y **ninguno lo mete en el dominio**.

## 1. Dónde viaja

| Lugar | Nombre | Quién lo escribe | Quién lo lee |
|---|---|---|---|
| Cabecera HTTP (cliente → BFF, BFF → servicio, BFF → cliente) | `X-Correlation-Id` | Cliente, BFF | BFF, servicios |
| Sobre del mensaje (campo del contrato Avro) | `correlation_id` | Los mapeadores (pasan `actual()` a `sobre()` / `_sobre()`) | Consumidores |
| Propiedad del mensaje Pulsar | `correlation_id` | `Despachador._publicar_mensaje` | Consumidores; `pulsar-admin peek-messages` |
| Línea de registro | `cid=<valor>` | `logging` (fábrica de registros) | Personas; `grep` |

Los dos lugares del mensaje (sobre y propiedad) llevan **siempre el mismo valor**: ambos salen de `correlacion.actual()`.

## 2. Reglas de validez y creación

- Forma válida: `^[A-Za-z0-9._:-]{1,64}$`. Cualquier otra cosa (vacío, > 64, espacios, saltos de línea, `|`, `=`) se trata como **ausente**.
- Ausente → **quien lo recibe lo crea** (`uuid4`) y lo propaga desde ahí. Vale para el BFF, para una llamada directa a la API de un servicio y para un mensaje publicado sin identificador (p. ej. por una herramienta).
- Un valor válido **nunca se modifica** en el camino.

## 3. Reglas por borde

| Borde | Comportamiento |
|---|---|
| **BFF, petición entrante** | Respeta o crea; lo envía en `X-Correlation-Id` a los servicios; lo devuelve en **toda** respuesta; en `POST /trabajos` y `POST /trabajos/asignacion` (`2xx`) lo agrega también al cuerpo |
| **Servicio, petición HTTP entrante** | `before_request`: lee `X-Correlation-Id` → valida o crea → fija el contexto. `after_request`: lo devuelve. `teardown_request`: restaura |
| **Servicio, mensaje consumido** | En `correr()`, alrededor de `manejar(...)`: precedencia campo `correlation_id` del sobre → propiedad `correlation_id` → crear. Cubre también el camino de error (`negative_acknowledge`) |
| **Servicio, mensaje publicado** | `Despachador`: `properties['correlation_id'] = actual()` (sustituye lo que haya pasado el handler). Los mapeadores pasan `correlation_id=actual()` a `sobre()`/`_sobre()`; `sobre()` no cambia (sigue idéntico a `contratos/v1/mensajes.py`) |
| **Registro** | `%(levelname)s %(name)s \| cid=%(correlation_id)s \| %(message)s`; fuera de contexto, `cid=-` |

## 4. Lo que NO cambia

| Elemento | Estado |
|---|---|
| Clave de partición (`partition_key`) | **Igual**: `trabajo_id` en los eventos de trabajo; `proveedor_id` en Acreditación; `trabajo_id` en Emparejamiento |
| Esquemas Avro / `contratos/` | **Igual**: `correlation_id` ya existe en los cinco contratos como `String(default=None, required_default=True)`; cambia el valor, no la forma |
| Tópicos, particiones, suscripciones | **Igual** |
| Dominio y tablas | **Sin** el identificador (FR-030) |
| Clientes que llaman directo a un servicio | Siguen funcionando; quedan identificados por quien recibe |

## 5. Cómo seguir una petición

```bash
CID=<valor devuelto en X-Correlation-Id, o en "correlation_id" de POST /trabajos>
docker compose logs --no-color -t | grep -F "$CID" | sort -t'|' -k2
```

Cada línea empieza con el contenedor, luego la marca de tiempo de Docker (que ordena), luego `LEVEL logger | cid=… | mensaje`. Una búsqueda devuelve los pasos de **todos** los servicios que atendieron esa petición.

Para inspeccionar el mensaje real en el broker (propiedades y `correlation_id` del sobre), ver `quickstart.md` §6.

## 6. Verificación (criterios)

| Criterio | Cómo |
|---|---|
| CA-2.16/2.17/2.17b | `test_correlacion.py` del BFF; carpeta 9 de Postman |
| CA-2.17c | `escenarios/bff.sh`: el valor de la respuesta aparece en logs y mensajes |
| CA-2.18 | `escenarios/bff.sh`: una búsqueda sobre una saga real recorre todos los servicios (*pendiente* hasta US-01 para los pasos de saga; los de creación → emparejamiento → seguimiento se verifican ya) |
| CA-2.19 | `escenarios/bff.sh`: `peek-messages` muestra propiedad y sobre |
| CA-2.20 | Prueba unitaria (`partition_key` literal) + `escenario-8.sh` sin cambios |
| CA-2.21 | `herramientas/verificar_aislamiento.py`: ninguna coincidencia de `correlation`/`correlacion` en `dominio/` ni en `dto.py` |
| CA-2.22 | `escenarios/bff.sh`: llamada directa sin cabecera y mensaje publicado con el campo vacío |
