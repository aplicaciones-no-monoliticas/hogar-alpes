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

---

## CON-1 · La herencia de `Record` pierde los campos del padre

**Fecha:** 2026-09-11 · **Dónde:** `contratos/v1/` · **Verificable con:** `python herramientas/verificar_contratos.py`

### El hallazgo

El metaclase de `pulsar.schema` arma los campos mirando **solo el diccionario propio** de la clase (`pulsar/schema/definition.py:47-65`). Los campos heredados **no entran al esquema**, y no hay error ni advertencia:

```
campos de Mensaje             : [id, time, ingestion, specversion, type, datacontenttype, service_name, correlation_id]
campos de ComandoIntegracion  : []          <-- solo hereda: se queda sin ningún campo
campos de ComandoCrearTrabajo : [trabajo_id, canal, partner_id, ...]   <-- sin sobre
```

### Lo que esto significa para el código que ya está en `main`

`EventoTrabajoCreado`, en Gestión de Trabajos, publica **un solo campo: `data`**. El sobre CloudEvents —`id`, `type`, `time`, `service_name`— **nunca ha viajado** en sus eventos de integración, pese a que la especificación lo daba por existente (`RS-2`) y el README lo describe.

No rompía nada porque todavía nadie consume esos eventos entre servicios. Se corrige en **GT-3**, cuando Gestión de Trabajos pase al stream unificado `evt-trabajo-{región}` con el contrato plano.

### Cómo apareció, y la lección que vale para la sustentación

La primera versión del verificador **daba PASA sin probar nada**. Comparaba `leido.correlation_id == instancia.correlation_id`: como ese campo no se deserializaba, ambos lados devolvían el mismo descriptor de clase, y la comparación era cierta de forma vacía. El defecto se vio porque al imprimir el valor salió `<pulsar.schema.definition.String object>` en lugar de un texto.

Una verificación que compara un objeto contra sí mismo siempre pasa. **Las aserciones van contra literales**, no contra los atributos del objeto que se acaba de publicar.

### La decisión

Cada contrato **repite los ocho campos del sobre de forma explícita**. Es duplicación deliberada, del mismo tipo que el seedwork copiado (`TO-7`): se prefiere repetición visible a una herencia que falla en silencio. Para que las copias no se desvíen, `herramientas/verificar_contratos.py` comprueba en los cinco contratos:

1. que todos los campos lleven `"default"` (regla de INF-0),
2. que el sobre esté completo, los ocho campos,
3. que el mensaje vuelva **con sus valores**, comparados contra literales.

Se descartó la alternativa de anidar el sobre como sub-record (`sobre = Mensaje()`), que sí funciona: deja los campos un nivel abajo y reintroduce la pregunta de cómo evoluciona un record anidado, justo lo que INF-0 nos costó resolver.

### Verificación ejecutada

| Contrato | Campos con default | Sobre | Ida y vuelta |
|---|---|---|---|
| `cmd-trabajo` | 18 / 18 | completo | 5 campos intactos |
| `evt-trabajo` | 17 / 17 | completo | 4 campos intactos |
| `cmd-acreditacion` | 17 / 17 | completo | 4 campos intactos |
| `evt-acreditacion` | 17 / 17 | completo | 4 campos intactos |
| `evt-emparejamiento` | 15 / 15 | completo | 4 campos intactos |

---

## INF-3 · La cuota de backlog está acoplada a la retención

**Fecha:** 2026-09-11 · **Dónde:** `infra/pulsar/` · **Verificable con:** `docker compose run --rm pulsar-config`

La política de backlog es la que sostiene la respuesta del escenario 6: al desalojar lo más viejo en vez de retener al productor, una caída larga del reactor **no degrada a Gestión de Trabajos**. Aplicarla costó tres intentos, y los tres motivos valen para la sustentación.

| Intento | Qué pasó | Causa real |
|---|---|---|
| 1 | `Need to provide just 1 parameter` | La bandera `--limitSize` no existe en 3.2.2: es `-l/--limit` |
| 2 | `HTTP 412 · Backlog Quota exceeds configured retention quota` | El script aplicaba la cuota **antes** que la retención, y Pulsar valida una contra otra |
| 3 | El mismo 412, con retención 10G y cuota 10G | La comparación es **estricta**: `10G < 10G` es falso |

**La decisión:** se dimensiona la retención **por encima** de la cuota (20G frente a 10G), no al revés. Recortar el backlog para que quepa en la retención habría encogido la ventana de la que depende el escenario 6, que es justamente lo que había que proteger.

**El guardia que quedó:** el script **relee la cuota del broker** al final y falla si no está. No basta con que el comando no haya protestado —durante dos corridas la política no existía y el broker aplicaba su valor por defecto en silencio—, y una cuota por defecto podría ser precisamente la que bloquea al productor.

### Lo que queda creado

Tenant `hogar-alpes`, tres namespaces con sus seis políticas, siete tópicos de 4 particiones y **nueve suscripciones pre-creadas sin ningún consumidor todavía**. Eso último es lo que permite afirmar el escenario 6: en Pulsar, un mensaje publicado en un tópico sin suscripciones no se retiene para nadie, así que si Operaciones nunca hubiera arrancado, sus eventos no existirían cuando por fin lo hiciera.

`conosur` no se crea aquí a propósito: se agrega en caliente durante el escenario 8, para medir que las regiones activas no se interrumpen (CA-8.4).

---

## INF-4 · Una región se define una sola vez

**Fecha:** 2026-09-11 · **Dónde:** `infra/pulsar/comun.sh`, `agregar-region.sh`

### La decisión

`crear_region` vive en `comun.sh` y la usan **los dos** scripts: la inicialización y el alta en caliente. Si el alta creara tópicos o suscripciones distintas de las que crea la inicialización, la región nueva quedaría sutilmente rota y **el escenario 8 estaría midiendo otra cosa**: la comparación entre regiones dejaría de ser válida justo en la medición que la sostiene.

Una región es, por definición única: dos tópicos particionados (`cmd-trabajo-<r>`, `evt-trabajo-<r>`) y tres suscripciones (`gestion-trabajos`, `operaciones`, `emparejamiento-<r>`).

### Qué significa «en caliente»

Agregar una región **no toca ningún tópico existente ni reinicia ningún servicio**. Operaciones la descubre sola, porque se suscribe por patrón (`evt-trabajo-.*`); Emparejamiento necesita levantar la réplica de esa región, que es una unidad de despliegue **nueva**, no un cambio en las que ya corren. Eso es lo que hace medible *«cero interrupciones en regiones activas»*.

### Verificación ejecutada

| Comprobación | Resultado |
|---|---|
| `inicializar.sh` después del refactor | `PASA` — el cambio no rompió la topología |
| Alta de `conosur` | 2 tópicos de 4 particiones y 3 suscripciones, **releídas del broker** |
| Segunda alta de `conosur` | Todo `existe` · `PASA` — idempotente |
| `andina` y `norteamerica` | Intactas: mismos tópicos y mismas suscripciones |
| Guardias: sin argumento · nombre inválido · alta válida | Salidas `2`, `2`, `0` |

### Otra verificación que casi pasa por buena

La primera comprobación de los códigos de salida imprimió `exit 0` para el caso sin argumento, y era falso: `$?` estaba capturando el `grep` de la tubería, no el script. Es el mismo error que en CON-1, donde una aserción comparaba un objeto contra sí mismo.

Vale la pena nombrarlo como patrón: **una verificación mal escrita no falla, pasa** — y una verificación que pasa por la razón equivocada es peor que no tenerla, porque genera confianza. Por eso los scripts de esta entrega releen del broker lo que crearon en lugar de confiar en que nadie protestó.

---

## GT-1 y GT-2 · Un candado no reentrante colgaba la primera publicación

**Fecha:** 2026-09-12 · **Dónde:** `servicios/gestion_trabajos`, `servicios/_plantilla`

### El defecto

`config/broker.py` reutiliza cliente y productor para no abrir una conexión por mensaje (brecha `G-3a`). La primera versión protegía ese estado con `threading.Lock`, y `productor()` tomaba el candado y llamaba a `cliente()`, **que volvía a tomar el mismo candado**. Un `Lock` de Python no es reentrante: la **primera** publicación se autobloqueaba.

Lo que se veía desde afuera era desconcertante: el `POST` se quedaba colgado hasta que gunicorn abortaba el worker por tiempo y devolvía `500`, sin una sola línea de error en el log —porque el mensaje de log venía *después* del `send`— y sin que el tópico llegara a crearse. La colección de Postman tardó **33 minutos** y falló 20 de 31 aserciones.

La corrección es `threading.RLock()`, en **las dos copias**: la plantilla y Gestión de Trabajos. Otra vez el costo de `TO-7`, y esta vez el arreglo era obligatorio en ambas.

### Por qué la verificación de INF-6 no lo atrapó

La plantilla se verificó arrancando la API, comprobando `/health` y probando el reintento del consumidor. Nada de eso **publica un evento**, así que el camino con el candado nunca se ejecutó. Es el tercer caso en esta entrega del mismo patrón: *una verificación que no ejercita el camino real pasa sin probar nada*.

La lección concreta: **verificar el camino que el escenario recorre**, no el que es fácil de montar. El escenario 8 publica eventos; la verificación de la plantilla no publicaba ninguno.

### Lo que quedó

| Cambio | Por qué |
|---|---|
| API y consumidor son **procesos distintos** de la misma imagen | Escalar consumidores sin chocar con el puerto HTTP (escenario 8) y detener el reactor sin tumbar su API (escenario 6) |
| El consumidor ya **no es un hilo** dentro de `create_app` | Con el recargador o con varios workers podía quedar duplicado, consumiendo el mismo comando dos veces |
| Cliente y productor **por proceso** | `G-3a`: antes se abría un cliente por mensaje |
| Cada evento viaja con **clave de partición** `trabajo_id` y **propiedades** `partner_id`, `region`, `correlation_id` | La clave preserva el orden por trabajo al particionar (escenario 8); las propiedades se leen sin deserializar y mitigan `TO-4` |

### Verificación ejecutada

| Comprobación | Resultado |
|---|---|
| Pruebas unitarias | 9 / 9 |
| Los dos procesos arriba | API responde `modo: api`; el consumidor queda suscrito a `cmd-trabajo` |
| El consumidor reintenta contra un broker inexistente | **18 reintentos** en 25 s, sin terminar el proceso |
| Publicación | 10 `POST` → **10 respuestas 202 y 10 eventos en el tópico** |
| Un productor **por proceso** | Con `WORKERS=1`: **1** productor · con 2 workers: **2** — no 10, que sería uno por mensaje |
| Colección de Postman | **18 peticiones, 36 aserciones, 0 fallos, 25,5 s** |

Los nombres de tópico siguen siendo los actuales: unificarlos en `evt-trabajo-{región}` es **GT-3**.

---

## ACR-1…5 · EMP-1…5 · Dos defectos que solo aparecieron con el clúster real corriendo

**Fecha:** 2026-09-13 · **Ejecutado por:** Juan Manuel Domínguez · **Dónde:** `servicios/acreditacion/`, `servicios/emparejamiento/` · **Cómo se encontraron:** levantando el clúster de Pulsar + Postgres de verdad (`docker compose up`, más un overlay temporal con `acreditacion` y `emparejamiento`, no commiteado) y probando los flujos HTTP y por tópico de punta a punta. Ninguno de los dos aparece en `pytest` porque los dos necesitan un broker real o dos procesos compitiendo — exactamente lo que las pruebas unitarias, a propósito, no usan.

### 1 · `config/broker.py` se autobloqueaba en el primer evento publicado

La plantilla (`INF-6`) protege `_cliente` y `_productores` con un solo candado (`threading.Lock`). `productor()` toma el candado y, **sin soltarlo**, llama a `cliente()` — que vuelve a tomar el mismo candado. Con un `Lock` no reentrante eso es un auto-interbloqueo del propio hilo: el primer request que publica un evento (el primero en necesitar crear el productor) se queda esperando un candado que él mismo ya tiene tomado, hasta que gunicorn lo mata por `WORKER TIMEOUT`.

No se veía en las pruebas de este servicio porque `tests/conftest.py` reemplaza `Despachador.publicar_evento` por un no-op (a propósito: la suite no depende de un broker). Tampoco se veía en el proceso `consumidor`, porque ahí `cliente()` se llama primero, sola, para suscribirse — y para cuando `productor()` la necesita, el candado ya está libre. Apareció exactamente donde tenía que aparecer: en el primer `POST /acreditaciones` contra el clúster real.

**Corrección**, en la copia de `config/broker.py` de los dos servicios nuevos: `threading.Lock()` → `threading.RLock()`. Un `RLock` es reentrante por hilo: el mismo hilo puede tomarlo dos veces sin bloquearse. `servicios/_plantilla` y `servicios/gestion_trabajos` (que todavía no ha migrado a este despachador, `GT-2`) tienen el mismo defecto latente y deberían corregirse igual cuando les toque.

### 2 · `vigencia_meses` no viajaba en el evento — Acreditación "olvidaba" cuánto duraba

`Acreditacion.aprobar()` calcula `vigente_hasta` a partir de `self.vigencia_meses`. El campo se fija en `solicitar()`, pero **el evento `AcreditacionSolicitada` no lo llevaba**: no estaba en la lista de campos del snapshot. Un comando `AprobarAcreditacion` real siempre corre sobre un agregado **reconstruido** (`repositorio.obtener_por_id`), y la reconstrucción reproduce el estado únicamente a partir de lo que cada evento trae. Resultado: `vigencia_meses` volvía a su valor por defecto (`0`) después de cualquier recarga, y toda aprobación fijaba `vigente_hasta = hoy`, sin importar los meses solicitados.

La primera versión de `test_agregar_y_reconstruir_coincide_con_el_estado_original` no lo agarró por la misma trampa que ya documentó `CON-1`: comparaba `reconstruida.vigente_hasta` contra `acreditacion.vigente_hasta`, y **las dos variables apuntaban al mismo objeto ya reconstruido** — la comparación era cierta de forma vacía. Se vio al probar contra HTTP real: `vigente_hasta` salía igual a la fecha de hoy sin importar `vigencia_meses`.

**Corrección:** `vigencia_meses` se agregó a `EventoAcreditacion` (el snapshot común a los tres eventos) y a `CAMPOS_EVENTO` del mapeador de persistencia, así que ahora viaja y se reconstruye igual que el resto del estado. La prueba se corrigió para comparar contra un **literal** (`date.today() + timedelta(days=360)`), no contra el valor que se está verificando.

### La lección que se repite

Las dos veces que este patrón —una prueba que compara un valor contra sí mismo, o contra otro que depende del mismo cálculo— apareció en la entrega (`CON-1`, `INF-4`, y ahora esto), la prueba **pasó** sin probar nada. Las pruebas de dominio de este servicio (`test_dominio_acreditacion.py`, `test_dominio_emparejamiento.py`) sí comparan contra literales desde el principio; las de infraestructura que no lo hacían se corrigieron al encontrarlas.

### Verificación ejecutada

| Comprobación | Resultado |
|---|---|
| `pytest` en `acreditacion` y `emparejamiento` tras las dos correcciones | 19 y 16 pruebas, todas en verde |
| `POST /acreditaciones` → `PUT /aprobar` → `GET` contra el clúster real | `vigente_hasta` = solicitud + 12 meses, no la fecha de hoy |
| `SolicitarAcreditacion` ×2 y `AprobarAcreditacion` ×2 por `cmd-acreditacion` (mismo `acreditacion_id`) | Solo 2 eventos en el store (versiones 1 y 2), solo 2 snapshots publicados en `evt-acreditacion`: la reentrega no duplicó nada |
| `TrabajoCreado` sintético en `evt-trabajo-andina` → `emparejamiento-andina` | Candidatos correctos desde la proyección, `CandidatosIdentificados` publicado en `evt-emparejamiento`; con una categoría sin proveedores acreditados, `SinCandidatos` |
| `evt-acreditacion` → proyección de Emparejamiento | `GET /candidatos` reflejó el proveedor aprobado por Acreditación, sin ninguna llamada síncrona entre los dos servicios |

---

## INT-1 y INF-5 · El sistema completo desde un clon limpio

**Fecha:** 2026-09-14 · **Verificable con:** `docker compose down -v && docker compose up -d --build`

### La topología descentralizada deja de ser una promesa

Cada servicio comparte red **únicamente** con el broker y con su propia base de datos: `red-trabajos`, `red-operaciones`, `red-acreditacion`, `red-emparejamiento`. Desde `gestion-trabajos`, el host `postgres-acreditacion` **ni siquiera resuelve**.

Eso importa para la sustentación: la respuesta a *«¿y cómo garantizan que un servicio no lee la base de otro?»* deja de ser «por disciplina del equipo» y pasa a ser «no hay ruta de red». Las 9 comprobaciones —cada servicio contra su base y contra dos ajenas— pasan.

Lo que **no** queda separado por red es servicio↔servicio: los cuatro comparten `red-broker` porque todos necesitan al broker. Esa parte se sostiene en que ninguna variable de entorno apunta a otro servicio y en que no hay clientes HTTP en el código; conviene decirlo así y no de más.

### El defecto que solo aparece en un arranque en frío

Con la base vacía, `api` y `consumidor` —dos procesos del mismo servicio— llaman ambos a `crear_app()` y ejecutan `create_all` a la vez. Los dos ven «la tabla no existe» y los dos emiten `CREATE TABLE`. PostgreSQL deja pasar al primero y el segundo muere con un error que no menciona tablas:

```
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint
"pg_type_typname_nsp_index"
DETAIL:  Key (typname, typnamespace)=(trabajos, 2200) already exists.
```

La API de Gestión de Trabajos quedó muerta con `Worker failed to boot`, mientras su consumidor seguía arriba. **Es una moneda al aire**: gana quien llegue primero, y el `docker compose up` del tutor decide cuál de los dos procesos se cae.

**Stiven y Juan Manuel ya lo habían encontrado y resuelto** en Operaciones, Acreditación y Emparejamiento, con un `_crear_tablas()` que reintenta —su comentario nombra el mismo índice del catálogo—. Los que quedaron atrás eran **Gestión de Trabajos y la plantilla**, y la plantilla era el peor de los dos: todo servicio futuro habría heredado el defecto. Se adoptó su misma solución, no una variante propia, para que las cuatro copias digan lo mismo.

Tercera vez en esta entrega que el mismo arreglo hay que hacerlo en varias copias —candado reentrante, contratos, creación de tablas—. Es el costo de `TO-7`, y ya no es un argumento teórico: son tres casos con nombre.

### Verificación ejecutada

| Comprobación | Resultado |
|---|---|
| `docker compose up` desde **volúmenes borrados** | Las 4 API responden en 8000, 8001, 8002 y 8003 |
| Contenedores muertos tras el arranque | Solo `pulsar-init` y `pulsar-config`, ambos con código 0: terminan por diseño |
| Topología recreada **sin intervención** | `PASA · topología creada` · 7 tópicos particionados · 9 suscripciones pre-creadas |
| Aislamiento de bases (CA-T1) | 9 de 9 |
| Pruebas | 9 Gestión de Trabajos · 20 Operaciones · 19 Acreditación · 16 Emparejamiento |

### Lo que todavía no cruza

Gestión de Trabajos publica en `public/default/evt-trabajo-creado`, mientras Operaciones y Emparejamiento escuchan en `hogar-alpes/trabajos/evt-trabajo-{región}`. El sistema **arranca completo, pero los eventos aún no llegan entre servicios**: eso lo cierra **GT-3**, y hasta entonces el escenario 6 no se puede medir de punta a punta.

---

## OPS-1…4 · HER-1 · ESC-6 · INT-2 · Operaciones consume por patrón, no por región

**Fecha:** 2026-09-14 · **Ejecutado por:** Stiven Cardona · **Dónde:** `servicios/operaciones/`, `herramientas/generador_carga.py`, `escenarios/escenario-6.sh`, `postman/`

### Por qué Operaciones no replica el modelo "una réplica por región" de Emparejamiento

Emparejamiento necesita una réplica por región porque su comando (`EmparejarTrabajo`) lee la proyección local y produce un resultado por trabajo: el paralelismo es la medida del escenario 8. Operaciones solo abre o actualiza un seguimiento — no hay nada que ganar particionando por región y sí algo que perder: una réplica por región multiplicaría contenedores sin que ningún criterio de aceptación lo pida. Por eso `config/topicos.py` arma un **patrón** (`evt-trabajo-.*`) y una sola suscripción durable (`operaciones`, Failover) lo cubre todo, incluida una región agregada en caliente (CA-8.4) sin redesplegar. Confirmado con el spike de `pulsar-client` (INF-0, pregunta P2 y el mecanismo de `pattern_auto_discovery_period`): el cliente acepta un `re.compile(...)` como argumento `topic` de `subscribe()`.

### La dependencia con GT-3/GT-4 que no se puede ocultar

`operaciones` consume el contrato de CON-1 (`evt-trabajo-{región}`, discriminado por `type`). Hoy Gestión de Trabajos **todavía publica en los tópicos viejos** (`evt-trabajo-creado` / `evt-trabajo-estado`, ver la nota de CON-1 arriba): GT-3 es lo que los unifica, y no está hecho. Es exactamente la misma situación que dejó documentada la nota de verificación de EMP-3 (`docs/03-tareas.md` §5).

**Consecuencia para las herramientas de esta entrega:**

- `herramientas/generador_carga.py` soporta tres caminos: `--via-http` (contra la API real de GT, mide su disponibilidad), `--topico cmd-trabajo-*` (el camino que describe el plan técnico §9, sin efecto hasta GT-4) y `--topico evt-trabajo-*` (publica el evento de integración directo, bypaseando GT — el mismo atajo de EMP-3).
- `escenarios/escenario-6.sh` corre los dos primeros caminos **en paralelo**: HTTP contra GT real para CA-6.1/CA-6.2, y publicación sintética en `evt-trabajo-{región}` para CA-6.3…CA-6.6. Cuando GT-3/GT-4 aterricen, el camino sintético sobra y el script se simplifica a un solo generador.

Esto no es una desviación silenciosa del plan: queda anotado en la cabecera del script y aquí, para que nadie lo confunda con que Operaciones "ya está integrado end-to-end".

### Por qué la idempotencia vive en el comando, no en la capa anticorrupción

`AbrirSeguimiento` y `RegistrarCambioEstado` comparten la misma tabla `eventos_procesados`, pero cada uno decide por sí solo si el evento ya se aplicó — no hay un `if` centralizado en `consumidores.py` que decida cuál handler invocar dos veces. La razón: la deduplicación por `evento_id` (reentrega exacta del mismo mensaje) y la deduplicación por `trabajo_id` (un `TrabajoCreado` repetido con `evento_id` distinto) son reglas de negocio de cada comando, no un detalle de transporte. Consecuencia verificada en las pruebas: una reentrega exacta **no** inserta una segunda fila en `eventos_procesados` (su clave primaria ya existe), así que el conteo por `resultado=DUPLICADO` solo crece con la segunda forma de duplicado, no con la primera — las dos sostienen el mismo criterio (CA-6.4), medidas de maneras distintas.

### Huérfano, no descartado (corrige G-2)

`RegistrarCambioEstado` sobre un `trabajo_id` sin seguimiento no lanza ni descarta: registra `HUERFANO` en `eventos_procesados` y confirma el mensaje igual. Es la corrección directa de la brecha G-2 (`docs/01-especificacion.md` §3): con el stream unificado y `trabajo_id` como clave esto no debería ocurrir en operación normal, pero **el consumidor no confía en que el orden dentro de la partición sea perfecto** — lo deja contable en vez de asumirlo.

### Verificación ejecutada

Este entorno de desarrollo no tenía Python 3.11 ni acceso a Docker; se instaló un intérprete 3.11.16 aislado con `uv` para no relajar el target de versión del Dockerfile (`python:3.11-slim`).

| Comprobación | Resultado |
|---|---|
| `pytest` de `operaciones` (Python 3.11.16) | **20 / 20** — dominio, comandos (aplicado/duplicado/huérfano/orden), capa anticorrupción con eventos sintéticos, API |
| Regresión de los otros tres servicios con el mismo intérprete | `gestion_trabajos` 9/9 · `emparejamiento` 16/16 · `acreditacion` 19/19 — sin cambios de comportamiento |
| `docker-compose.yml` con `postgres-operaciones` + `operaciones` + `operaciones-consumidor` | YAML válido, servicios y volumen nuevos verificados por `python3 -c "yaml.safe_load(...)"` |
| `escenarios/escenario-6.sh` | `bash -n` (sintaxis) — **no** se corrió contra un clúster real: no hay Docker disponible en este entorno. Pendiente antes de la corrida formal |
| `herramientas/generador_carga.py` | Importa y corre en modo `--via-http` contra un puerto cerrado: reporta la falla de conexión correctamente (`FALLA`, código de salida 1) |
| `postman/hogar-alpes.postman_collection.json` | JSON válido tras la reestructuración; **no** se corrió con `newman` (requiere el sistema completo arriba) |

**Pendiente antes de la corrida formal de ESC-6** (a cargo de quien tenga Docker a mano): `docker compose up -d`, correr `escenarios/escenario-6.sh` de punta a punta y confirmar los seis criterios de aceptación contra el clúster real.
