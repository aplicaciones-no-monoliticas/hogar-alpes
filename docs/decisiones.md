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

---

## INF-2 · Clúster de Pulsar: dos consecuencias verificadas

**Fecha:** 2026-09-11 · **Estado del clúster:** `cluster-hda` con 1 ZooKeeper, **2 bookies** y **2 brokers** sanos, quórums ensemble 2 / escritura 2 / confirmación 2.

### 1. Las herramientas que corren desde el host necesitan `listener_name="external"`

Cada broker anuncia dos direcciones: `internal:pulsar://broker-N:6650` para quien vive en la red de Docker, y `external:pulsar://localhost:665X` para quien llama desde el host. Un cliente que no elige listener recibe la interna y falla, porque `broker-2` no resuelve fuera de Docker.

| Desde el host | Resultado |
|---|---|
| `pulsar.Client('pulsar://localhost:6650')` | **Falla** — `ConnectError`, tras intentar `pulsar://broker-2:6650` |
| `pulsar.Client('pulsar://localhost:6650', listener_name='external')` | **Publica** |

**Regla:** todo lo que corra desde el host —`spike_esquemas.py`, `generador_carga.py`, `medir_latencia.py`— usa `listener_name="external"`. Los servicios, que corren dentro de Docker, no lo usan.

No es un rodeo: es la forma en que Pulsar resuelve que un mismo broker se vea distinto desde adentro y desde afuera del clúster. En AWS será igual, con la IP pública como dirección externa.

### 2. Sin creación automática de tópicos, la brecha G-3b deja de ser teórica

El clúster tiene `allowAutoTopicCreation=false` (los tópicos los crea el script de INF-3). Con esa configuración, el código actual de Gestión de Trabajos muestra dos comportamientos que conviene ver ahora y no el día de la sustentación:

| Qué pasa | Evidencia | Cuándo se corrige |
|---|---|---|
| El evento de integración **se pierde en silencio**: el despachador registra `WARNING · No se pudo publicar en evt-trabajo-creado: TopicNotFound` y el `POST` igual responde `202` | Brecha **G-3b** de la especificación | INF-3 crea los tópicos. La pérdida ante un broker caído queda como riesgo **R-3** (fuera de alcance: es *outbox*) |
| El consumidor de comandos **muere y no vuelve**: `Error suscribiéndose al tópico de comandos · TopicNotFound`, y el hilo termina | `consumidores.py:57-60` atrapa la excepción fuera del bucle | **GT-1**: el consumidor pasa a proceso propio y debe reintentar la suscripción, no rendirse |

La segunda es un defecto real que no estaba en la lista de brechas: hoy, cualquier error transitorio del broker al arrancar deja el servicio sin consumir comandos **para siempre**, sin que nadie se entere. Se agrega al alcance de GT-1.

### 3. `public/default` queda como namespace de experimentos

La creación automática de tópicos se habilita **solo** en `public/default`, para que los experimentos —el spike, y mañana las pruebas sueltas— no tengan que pedir sus tópicos por adelantado. Los namespaces de la solución (`hogar-alpes/*`, que crea INF-3) la mantienen **deshabilitada**: ahí un nombre mal escrito debe fallar, no crear un tópico fantasma sin particiones ni suscripciones.

Con esa configuración, el spike se volvió a correr **contra el clúster** (no contra el standalone) y dio los cinco mismos resultados: el hallazgo de `required_default` no era un artefacto del entorno de desarrollo.

---

## INF-6 · La plantilla de servicio es una carpeta que se copia

**Fecha:** 2026-09-11 · **Dónde:** `servicios/_plantilla/`

### Carpeta copiable, no generador

Se evaluó un script generador y se descartó: **esconder el copiado sería esconder justo lo que hay que defender.** La decisión `TO-7` de la Entrega 2 es que el seedwork se duplica por servicio para no reintroducir acoplamiento en tiempo de compilación (`PS-8`), y un repositorio donde se ve `cp -r servicios/_plantilla servicios/<nombre>` cuenta esa decisión sin necesidad de explicarla.

### El seedwork ya no sabe cómo se llama su paquete

La versión de Gestión de Trabajos tenía la ruta absoluta escrita adentro (`from gestion_trabajos.config.uow import ...`), así que cada copia obligaba a editar el código base. En la plantilla esos imports son relativos (`from ...config.uow import ...`): **renombrar la carpeta basta**. Bajó el costo de la copia sin tocar la decisión.

También se corrigió una fuga: el seedwork común declaraba `TipoObjetoNoExisteEnDominioTrabajosExcepcion` —el nombre de un dominio ajeno en el código compartido— y las fábricas de `operaciones` ya la estaban importando. En la plantilla es `TipoObjetoNoExisteEnDominioExcepcion`.

### Los servicios nuevos nacen sin los dos defectos que ya encontramos

| Defecto | Cómo nace la plantilla |
|---|---|
| `G-3a`: un cliente de Pulsar por mensaje | Un cliente y un productor por proceso, en `config/broker.py` |
| El consumidor muere ante un fallo transitorio (INF-2) | `consumidor.py` reintenta la suscripción; el fallo del handler hace `negative_acknowledge`, no se pierde el mensaje |

Como efecto de `TO-7`, esos dos arreglos hay que hacerlos **otra vez** en Gestión de Trabajos (`GT-1`, `GT-2`): es exactamente el costo que la decisión dice que se paga, y conviene nombrarlo así en la sustentación.

El despachador además acepta **clave de partición** y **propiedades** (`partner_id`, `region`, correlación), que son lo que sostienen el orden por `trabajoId` del escenario 8 y la trazabilidad de `TO-4`.

### Verificación ejecutada

| Comprobación | Resultado |
|---|---|
| Arranca en modo API y responde `/health` | 200 · `{"status":"up","modo":"api"}` |
| El procedimiento de copiado del README, tal como está escrito | 0 menciones residuales a la plantilla; el servicio renombrado responde con su propio nombre |
| El consumidor reintenta en vez de morir | 4 reintentos en 12 s contra un broker inexistente |

`operation_timeout_seconds` quedó configurable (`BROKER_TIMEOUT`), porque con los 15 s por defecto la prueba del reintento no alcanzaba a observar el primer fallo.
