# Contrato: `cmd-trabajo-{región}` y `evt-trabajo-{región}` (sin cambios de esquema)

**Ningún campo Avro nuevo.** La única adición es una **propiedad de mensaje** (metadato de
Pulsar, fuera del esquema), que no requiere tocar `contratos/v1/cmd_trabajo.py` ni
`contratos/v1/evt_trabajo.py`.

## Propiedad nueva: `simular_fallo`

| | |
|---|---|
| Dónde entra | `POST /trabajos`, campo JSON opcional `simular_fallo` |
| Valores válidos | `SIN_CANDIDATOS` \| `VIGENCIA` \| `ASIGNACION` (cualquier otro valor, o ausente, se trata como flujo normal) |
| Cómo viaja | `propiedades['simular_fallo']` en cada mensaje publicado de la cadena (`cmd-trabajo`, `evt-trabajo`, `evt-emparejamiento`, `evt-acreditacion`), igual mecanismo que ya usa `correlation_id` como propiedad además de campo del sobre |
| Quién la lee | El handler que decide en cada punto de falla (ver `research.md` D3) |
| Quién la ignora | Todos los demás — es opcional y no forma parte del contrato de negocio (Assumptions del spec: "no se documenta como funcionalidad del producto") |

`evt-trabajo` gana **una transición nueva** desde el estado existente `CREADO` hacia
`EMPAREJANDO` (ya declarada en `TRANSICIONES`, solo que hoy nada la dispara) y usa
`TIPO_ESTADO_CAMBIADO` (existente) para las transiciones `EMPAREJANDO→ASIGNADO` y
`EMPAREJANDO→CANCELADO`. Ver `data-model.md` para el diagrama de transición completo. No hay
`type` nuevo en este stream.
