# Contratos de mensajes · v1

Definición canónica de los cinco streams del sistema. **La fuente de verdad es el registro de esquemas del broker**, no este código: aquí vive la versión de referencia en Python, que cada servicio **copia** a su propio `modulos/<contexto>/infraestructura/schema/v1/`.

Se copia y no se comparte por la misma razón que el seedwork (`TO-7`): un paquete común volvería a acoplar los cuatro servicios en tiempo de compilación. Esta carpeta existe para que las copias no se desvíen sin que nadie lo note.

## La regla que no se puede olvidar

```python
campo = String(default=None, required_default=True)
```

**Todo campo se declara así.** Si falta `required_default=True`, el esquema Avro sale sin `"default"` y el broker **rechaza** la primera evolución que agregue un campo. Lo verificamos en INF-0 (`docs/decisiones.md`): sin default, `IncompatibleSchema`; con default, aceptado y con las dos versiones guardadas en el registro.

`herramientas/verificar_contratos.py` comprueba esta regla en los cinco contratos, además de publicar y leer un mensaje de cada uno.

## Los cinco streams

| Módulo | Stream | Tipo de evento | Clave de partición |
|---|---|---|---|
| `cmd_trabajo.py` | `cmd-trabajo-{región}` | Comando | `trabajo_id` |
| `evt_trabajo.py` | `evt-trabajo-{región}` | **Integración** (delta) | `trabajo_id` |
| `cmd_acreditacion.py` | `cmd-acreditacion` | Comando | `proveedor_id` |
| `evt_acreditacion.py` | `evt-acreditacion` | **Carga de estado** (snapshot) | `proveedor_id` |
| `evt_emparejamiento.py` | `evt-emparejamiento` | Integración | `trabajo_id` |

Por qué cada tipo, en `01-especificacion.md` §6.1. En corto: `evt-trabajo` comunica hechos que disparan comportamiento y debe ser pequeño, porque el escenario 6 obliga a retener backlog; `evt-acreditacion` lleva el estado completo para que la proyección de Emparejamiento responda **sin preguntarle nada** a Acreditación y converja aunque se pierda un evento.

## El sobre

`mensajes.py` define la envolvente al estilo CloudEvents que heredan todos: `id`, `type`, `specversion`, `time`, `ingestion`, `datacontenttype`, `service_name` y `correlation_id`.

`correlation_id` es nuevo en esta entrega y responde a `TO-4`: en un sistema distribuido, el troubleshooting deja de ser una traza de pila y pasa a ser correlación de eventos entre procesos. Sin ese identificador, un incidente es inauditable.

`type` lleva la versión semántica del evento: `hogaralpes.trabajo.creado.v1`.

## Evolución

| Cambio | Qué hacer |
|---|---|
| Agregar o quitar un campo **opcional con default** | Mismo stream. El registro lo acepta como versión nueva |
| Renombrar un campo, cambiar su tipo o su significado | **Stream nuevo** `<nombre>-v2`, publicación dual durante la migración, y se retira `v1` cuando vence su TTL |

La regla de compatibilidad del namespace es `FULL_TRANSITIVE`: productores y consumidores se despliegan en cualquier orden —MOD-3 exige redesplegar un servicio solo— y un consumidor que vuelve de una caída (escenario 6) lee backlog escrito con cualquier versión de los últimos 7 días.

Los valores de dominio abiertos —estado, categoría— viajan como **texto**, no como enumeración Avro: una enumeración cerrada rompería MOD-3.
