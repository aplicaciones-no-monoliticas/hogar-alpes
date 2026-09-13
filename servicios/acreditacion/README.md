# Acreditación

Microservicio nuevo (`01-especificacion.md` §4.4). Contexto acotado
**Acreditación**: subdominio núcleo — *la confianza es el diferenciador*.
Copiado de `servicios/_plantilla` (`INF-6`); ver el README de esa carpeta para
lo que trae en común con los otros tres servicios.

## Modelo: Event Sourcing

A diferencia de Gestión de Trabajos, Operaciones y Emparejamiento (CRUD), este
servicio persiste **eventos**, no filas de estado (`D-5`). La tabla
`eventos_acreditacion` es append-only: cada fila es
`(agregado_id, version, tipo, datos, ocurrido_en)`, con
`UNIQUE(agregado_id, version)` como control de concurrencia optimista.

- **Escritura**: `SolicitarAcreditacion` → `AprobarAcreditacion` →
  `RevocarAcreditacion`. Cada comando carga el agregado reproduciendo su
  historial, valida la transición y, si es válida, añade un evento nuevo con
  `version + 1`.
- **Lectura**: `GET /acreditaciones/{id}` reconstruye el estado desde el log;
  `GET /acreditaciones/{id}/eventos` expone el historial completo — es la
  evidencia de que el Event Sourcing es consultable, no solo escribible.
- **Idempotencia ante reentrega**: `SolicitarAcreditacion` con el mismo
  `acreditacion_id` no crea una segunda acreditación; `Aprobar`/`Revocar`
  sobre un estado que ya es el destino no rompen la regla de transición —son
  la misma orden llegando dos veces, no un error.

## Integración

- **Comandos** (`cmd-acreditacion`, Failover, clave `proveedor_id`): los
  mismos tres, por tópico y por HTTP (§4.4 de la especificación) — ambos
  caminos ejecutan el mismo comando de aplicación.
- **Eventos publicados** (`evt-acreditacion`, carga de estado): cada
  transición publica el **snapshot completo** del agregado, después del
  commit. Lo consume la proyección de Emparejamiento (escenario 8).

## Endpoints

| Método | Ruta | Comando/consulta |
|---|---|---|
| `POST` | `/acreditaciones` | `SolicitarAcreditacion` (202) |
| `PUT` | `/acreditaciones/{id}/aprobar` | `AprobarAcreditacion` (202) |
| `PUT` | `/acreditaciones/{id}/revocar` | `RevocarAcreditacion` (202) |
| `GET` | `/acreditaciones/{id}` | Estado reconstruido (200/404) |
| `GET` | `/acreditaciones/{id}/eventos` | Historial (200/404) |
| `GET` | `/health` | — |

## Pruebas

```bash
pip install -r requirements.txt
pytest
```

Corren contra SQLite en memoria (sin PostgreSQL) y sin broker: la publicación
se reemplaza por un no-op en `tests/conftest.py`. La integración real contra
Pulsar se verifica con `herramientas/verificar_contratos.py` y
`escenarios/esquemas.py`, contra un clúster vivo.
