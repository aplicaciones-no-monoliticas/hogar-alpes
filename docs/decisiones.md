# Decisiones de implementación — Entrega 4

Anexo vivo: aquí se anota toda decisión que se toma **durante** la implementación y que no estaba cerrada en `02-plan-tecnico.md`. Es material de sustentación.

---

## INF-0 · Evolución de esquemas en `pulsar-client 3.5.0`

**Fecha:** 2026-09-11 · **Ejecutado por:** Andrés Gómez · **Reproducible con:** `python herramientas/spike_esquemas.py` contra un broker en `localhost:6650`

El plan (§2.5) dejaba tres preguntas abiertas sobre el cliente de Python, porque de ellas depende cómo se escriben **todos** los contratos. Se respondieron con un experimento, no con una suposición.

### Lo que se encontró

| # | Pregunta | Resultado |
|---|---|---|
| **A** | ¿El esquema generado por `Record` incluye `"default"`? | **Solo si el campo se declara con `required_default=True`.** `String()` y `String(default='')` generan `{"name": "a", "type": ["null", "string"]}`, **sin** default. `String(default=None, required_default=True)` genera `{"name": "a", "default": null, "type": ["null", "string"]}`. La causa está en `pulsar/schema/definition.py:143-154`: el `default` se emite únicamente cuando `field.required_default()` es verdadero |
| **B** | Sin `default`, ¿se puede agregar un campo opcional? | **No.** El broker responde `IncompatibleSchema`. Avro exige un valor por defecto para considerar compatible un campo agregado o quitado |
| **C** | Con `default`, ¿se puede? | **Sí.** El registro guarda la versión 0 (`a`, `b`) y la versión 1 (`a`, `b`, `c`), verificado con `pulsar-admin schemas get --version 0 \| 1` |
| **D** | ¿El consumidor lee en las dos direcciones? | **Sí, las dos.** Un lector nuevo sobre un dato viejo obtiene `c=None`; un lector viejo sobre un dato nuevo lee sus campos sin error |
| **E** | ¿El broker rechaza un cambio de tipo? | **Sí.** `String` → `Long` es rechazado con `IncompatibleSchema`. **CA-E2 es demostrable** |
| **P2** | ¿Orden de los campos? | **Orden de declaración.** El atributo `_sorted_fields` puede volverlo alfabético (`definition.py:139-142`); **no se usa** |

La estrategia de compatibilidad del namespace estaba en `UNDEFINED`, es decir, heredando el valor por defecto del broker. Se fija **explícitamente** en `FULL_TRANSITIVE`, que es lo que pedía RS-3: la regla de compatibilidad no puede ser la que venga de fábrica.

### La regla que queda (obligatoria para CON-1 y para todo contrato nuevo)

1. **Todo campo de un contrato se declara `Tipo(default=None, required_default=True)`.** Sin eso, el primer intento de evolucionar el esquema lo rechaza el broker.
2. Los campos nuevos se agregan **al final**. Avro no lo exige una vez que hay defaults, pero mantiene los diffs legibles y el orden del esquema estable.
3. **No** usar `_sorted_fields`.
4. **No** usar enumeraciones Avro para valores de dominio abiertos como estado o categoría: viajan como texto (RS-5). Una enumeración cerrada rompería MOD-3.
5. Cambio de tipo, renombre o cambio de significado → **stream nuevo `-v2`** (RS-4). El broker no lo deja pasar de otra forma, y eso es una garantía, no un obstáculo.

### Consecuencia inmediata sobre el código existente

Los contratos actuales de `gestion_trabajos` —`seedwork/infraestructura/schema/v1/mensajes.py`, `modulos/trabajos/infraestructura/schema/v1/{eventos,comandos}.py`— declaran sus campos como `String()`, **sin default**. Tal como están, agregar `trabajo_id` a `ComandoCrearTrabajo` (la demostración CA-E1, tarea GT-4) sería rechazado por el broker.

**Acción:** CON-1 reescribe los cinco contratos con la regla de arriba, y los contratos existentes se migran con ella. Como los streams nuevos (`evt-trabajo-{región}` bajo el tenant `hogar-alpes`) se crean desde cero, no hay esquema viejo registrado que estorbe.

### Por qué importa para la sustentación

Responde con evidencia a dos preguntas que el tutor puede hacer:

- *«¿Cómo saben que su esquema puede evolucionar sin romper a los consumidores?»* → Está probado en las dos direcciones, y el registro guarda las dos versiones.
- *«¿Qué pasa si alguien publica un cambio incompatible?»* → El broker lo rechaza. No depende de que el equipo se acuerde de revisarlo.
