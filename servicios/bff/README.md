# BFF — un solo punto de entrada

Componente de **borde**: la puerta por la que entran los clientes. No es un
microservicio de dominio.

- **Sin base de datos, sin broker, sin estado.** No guarda nada y no publica ni
  consume mensajes; se puede levantar en una o diez copias sin coordinación.
- **Mismas tecnologías que el resto**: Python 3.11, Flask y gunicorn (mismos
  pines). Las llamadas hacia adentro usan la biblioteca estándar (`urllib`,
  `concurrent.futures`); no hay ningún framework nuevo.
- **Puerto `8090`** en el host (`PUERTO_BFF`). El `8080` lo publica `broker-1`.

## Por qué existe

1. **Una sola dirección.** Un cliente no necesita saber en qué puerto vive cada
   servicio, ni que el sistema está dividido así.
2. **Consultas compuestas.** «¿Cómo va este trabajo?» hoy exige cuatro
   llamadas a cuatro servicios; aquí es una.
3. **Trazabilidad.** El BFF crea el identificador de correlación que el resto
   del sistema copia en sus mensajes y en sus registros.

Llamar directo a cada servicio **sigue siendo válido**: el BFF es una puerta
adicional, no obligatoria. Los cinco servicios de dominio siguen sin poder
llamarse entre sí; el BFF es el único que hace HTTP hacia adentro.

## Rutas de reenvío (17)

Misma ruta, mismo cuerpo, mismo código de respuesta que si se llamara al
servicio. Los errores de negocio (`400`, `404`, `409`) llegan sin cambios.

| Grupo | Ruta | Servicio | Variable |
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

`GET /health` es el **del propio BFF** (`{"status":"up","service":"bff"}`), no
se reenvía.

> Las tres rutas de `saga-log` están registradas, pero el servicio lo entrega
> US-01. Mientras no exista responden `503` nombrándolo.

**Una salvedad al «mismo cuerpo»:** `POST /trabajos`, cuando el servicio
responde `2xx` con un objeto JSON, recibe además el campo `correlation_id`
(solo se **agrega**; nunca se cambia ni se quita nada, y los errores no se
tocan).

## Endpoints compuestos (4)

Las llamadas se hacen **en paralelo**, cada una con su propio tiempo límite, y
la respuesta **degrada parcialmente**: cada parte lleva un estado.

| Estado de una parte | Significa |
|---|---|
| `DISPONIBLE` | El servicio respondió; `datos` es su cuerpo, sin modificar |
| `TODAVIA_NO_DISPONIBLE` | El servicio respondió `404` para algo derivado (seguimiento, emparejamiento, saga de un trabajo recién creado): consistencia eventual, no un error |
| `NO_DISPONIBLE` | No respondió, agotó el tiempo o dio `5xx`; trae `servicio` y `motivo` |

| Ruta | Qué devuelve |
|---|---|
| `GET /trabajos/{id}/completo` | `partes`: `trabajo`, `seguimiento`, `emparejamiento`, `saga` |
| `GET /proveedores/{id}/completo` | `partes`: `acreditacion`, `historial`, `candidato` (¿aparece hoy como candidato? una consulta por categoría). **`{id}` es el id de la acreditación** (el que devuelve `POST /acreditaciones`), no el `proveedor_id` |
| `GET /estado-del-sistema` | Salud de los seis componentes (`UP`/`DOWN`) y el resumen de sagas; `estado_general` `OK`/`DEGRADADO`. **Siempre `200`**, incluso con todo caído |
| `POST /trabajos/asignacion` | Crea el trabajo igual que `POST /trabajos` y agrega `seguimiento_saga` y `seguimiento_completo` |

Reglas de código: si el recurso **raíz** no existe (`trabajo`, `acreditacion`)
el `404` del servicio llega tal cual y sin `partes`; si **todas** las partes
fallan, `503` con la lista de servicios; en cualquier otro caso, `200`.

## Errores propios

Siempre JSON, con `correlation_id`, **nunca** una traza ni el texto crudo de un
servicio.

| Situación | Código | Cuerpo |
|---|---|---|
| Un servicio no responde (conexión rechazada, no resuelve, tiempo agotado) | `503` | `servicio`, `motivo` (`CONEXION_RECHAZADA` · `DNS` · `TIMEOUT`) |
| Un servicio responde `5xx` | `502` | `servicio`, `status_upstream`; el cuerpo del servicio no se reenvía |
| La ruta no existe | `404` | `grupos_disponibles` |
| La ruta existe con otro método | `405` | `metodos_permitidos` |
| Error no previsto en el BFF | `500` | `Error interno del BFF` (la traza va solo al registro) |

Un servicio caído no tumba las rutas de los demás. El tiempo límite cubre
también la resolución del nombre.

## Configuración

Todo por variables de entorno, con valores por defecto que funcionan en Compose:
cambiar a AWS o a Kubernetes no exige tocar código.

| Variable | Por defecto | Para qué |
|---|---|---|
| `URL_TRABAJOS` | `http://gestion-trabajos:5000` | Gestión de Trabajos |
| `URL_OPERACIONES` | `http://operaciones:5000` | Operaciones |
| `URL_ACREDITACION` | `http://acreditacion:5000` | Acreditación |
| `URL_EMPAREJAMIENTO` | `http://emparejamiento:5000` | Emparejamiento |
| `URL_SAGAS` | `http://saga-log:5000` | Registro de sagas (US-01) |
| `TIMEOUT_REENVIO_S` | `5` | Tiempo límite por llamada de reenvío |
| `TIMEOUT_COMPUESTO_S` | `1.5` | Tiempo límite por llamada de un compuesto |
| `WORKERS` / `THREADS` | `2` / `8` | Procesos e hilos de gunicorn (`gthread`) |
| `LOG_LEVEL` | `INFO` | Nivel de registro |
| `PUERTO_BFF` | `8090` | Puerto publicado en el host (Compose) |

## Cómo seguir una petición por los registros

Cada petición recibe un identificador de correlación: el que traiga el cliente
en la cabecera `X-Correlation-Id` (si tiene la forma `[A-Za-z0-9._:-]{1,64}`) o
uno nuevo. El BFF lo **devuelve en toda respuesta** —también en las de error—
y, en `POST /trabajos` y `POST /trabajos/asignacion`, en el campo
`correlation_id` del cuerpo. Todos los servicios lo copian en cada mensaje que
publican y en cada línea de registro.

```bash
CID=<valor de X-Correlation-Id, o del campo correlation_id>
docker compose logs --no-color -t | grep -F "$CID" | sort -t'|' -k2
```

Una sola búsqueda devuelve los pasos de **todos** los servicios que atendieron
esa petición, en orden de marca de tiempo. El límite conocido: el orden entre
contenedores depende de que compartan reloj (mismo anfitrión en Compose; en
Kubernetes conviene un agregador que ordene por tiempo).

**La vida de un trabajo** abarca varias peticiones, cada una con su propio
`cid=`. Para seguirla, buscar el trabajo: las líneas que lo tocan llevan
`trabajo_id=<id>`.

```bash
docker compose logs --no-color -t | grep -F "trabajo_id=<id>"
```

El identificador es información de transporte: no aparece en las entidades de
dominio ni en ninguna tabla, y **no es la clave de partición** (esa sigue siendo
el id del trabajo).

## Pruebas

```bash
cd servicios/bff && python -m pytest        # servidores HTTP falsos reales; no necesita los servicios
python herramientas/verificar_aislamiento.py  # comprobaciones estáticas
bash escenarios/bff.sh                        # contra el sistema levantado
newman run postman/hogar-alpes-bff.postman_collection.json -e postman/bff-local.postman_environment.json
```
