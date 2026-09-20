# saga_log

Servicio de solo lectura sobre la saga de asignación de un trabajo (Entrega 5).
Nace copiando `servicios/_plantilla/` (decisión `TO-7`). Observa los tres
streams existentes —`evt-trabajo-{región}`, `evt-emparejamiento`,
`evt-acreditacion`— y nunca publica nada (CA-1.16).

Ver `specs/002-saga-asignacion-trabajo/` para el diseño completo (plan,
research, data-model, contratos, quickstart).

## Qué expone

- `GET /sagas/{trabajo_id}` — estado y línea de tiempo de una transacción.
- `GET /sagas?estado=` — todas las transacciones en un estado dado.
- `GET /sagas/resumen` — conteo por estado.
- `GET /health`.

## Los dos modos del proceso

```bash
MODO=api         # gunicorn, puerto 5000
MODO=consumidor  # python -m saga_log.consumidor
```
