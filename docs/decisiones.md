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

---

## GT-3 · Los eventos cruzan entre servicios por primera vez

**Fecha:** 2026-09-14 · **Dónde:** `servicios/gestion_trabajos/`

Hasta aquí, los cuatro servicios corrían pero hablaban idiomas distintos en tópicos distintos: Gestión de Trabajos publicaba dos records con carga anidada en `public/default/evt-trabajo-creado` y `evt-trabajo-estado`, mientras Operaciones y Emparejamiento escuchaban el `EventoTrabajo` plano de CON-1 en `hogar-alpes/trabajos/evt-trabajo-{región}`.

### Qué cambió

| Antes | Ahora |
|---|---|
| Dos tópicos, uno por tipo de evento | **Un stream por región**, los dos tipos discriminados por `type` |
| `public/default`, sin particionar | `hogar-alpes/trabajos`, 4 particiones, clave `trabajo_id` |
| Dos records con `data` anidado, heredando un sobre que no viajaba | El `EventoTrabajo` **plano** de `contratos/v1`, con los ocho campos del sobre |
| Suscripción `gestion-trabajos-sub-comandos` | `gestion-trabajos`, **la que la infraestructura pre-crea** |
| País → región escrito en el handler | `config/topicos.py`, con `REGIONES_EXTRA` por variable de entorno |

Lo de la suscripción no es cosmético: con el nombre viejo, la suscripción que `inicializar.sh` pre-crea quedaba huérfana, y los comandos publicados antes de que el servicio arrancara no se retenían para nadie — justo la garantía que el escenario 6 necesita.

### El evento de dominio tuvo que aprender dónde ocurrió

`EstadoTrabajoCambiado` solo llevaba `trabajo_id`, `estado_anterior` y `estado_nuevo`. Sin `pais` no había con qué enrutarlo, y si la creación y el cambio de estado caían en streams distintos **se perdía el orden dentro del trabajo**, que es exactamente lo que la brecha `G-2` describe. Ahora el evento lleva su contexto (`pais`, `ciudad`, `canal`, `partner_id`, `categoria`, `urgencia`), lo que además evita que el consumidor tenga que preguntarle nada a este servicio.

### Verificación ejecutada

| Comprobación | Resultado |
|---|---|
| `POST /trabajos` (CO) | `202` · publicado en `evt-trabajo-andina` |
| Fan-out del stream | **1 mensaje entrando, 2 saliendo**: las dos suscripciones, cada una con su cursor |
| Operaciones abre el seguimiento **por Pulsar** | `200` · prioridad `P1`, SLA 60 min derivados de la urgencia |
| Cambio de estado por el **mismo** stream | El seguimiento pasa de `CREADO` a `EMPAREJANDO`: llegó después de la creación, en orden (`G-2`) |
| Emparejamiento reacciona con su propia suscripción | `200` · `region: andina`, `total: 0` — correcto: la base arrancó en frío y no hay acreditaciones cargadas, así que la rama legítima es «sin candidatos» |
| Tópicos viejos | 0: ya no existen |
| Enrutamiento por país | CO→andina · MX→norteamerica · BR y AR→conosur · PE→por defecto |

### Lo que esto desbloquea

`escenario-6.sh` publicaba eventos sintéticos directo en `evt-trabajo-{región}` porque GT no llegaba hasta allí. **Ese atajo ya no hace falta**: el camino real —`POST /trabajos` → Pulsar → Operaciones— está probado de punta a punta, así que el escenario 6 puede medirse contra el sistema de verdad, que es lo que el tutor va a querer ver. (Nota de edición: había dos filas de tabla y una frase duplicadas de la sección OPS-1…4 colgando al final de este archivo — se quitaron, el contenido ya está arriba.)

**Sigue pendiente antes de la corrida formal de ESC-6** (a cargo de quien tenga Docker a mano): `docker compose up -d`, correr `escenarios/escenario-6.sh` de punta a punta contra el sistema real y confirmar los seis criterios de aceptación — ahora con el camino sintético de por medio ya no siendo necesario, según lo de arriba.

---

## GT-4…7 · ESC-M · ESC-E · DEP-1 · DOC-1 · Cerrando el ciclo de Gestión de Trabajos

**Fecha:** 2026-09-14 · **Dónde:** `servicios/gestion_trabajos/`, `escenarios/`, `infra/aws/`, `infra/sidecar/`, `README.md`

### El consumidor de comandos ya existía; el contrato que usaba, no

`gestion_trabajos` ya tenía, desde antes de esta entrega, un consumidor Shared suscrito por patrón a `cmd-trabajo-.*` (`infraestructura/consumidores.py`). Lo que le faltaba a GT-4 no era ese mecanismo: era que su copia del contrato (`schema/v1/comandos.py`) seguía siendo la versión pre-CON-1 —`ComandoCrearTrabajo(ComandoIntegracion)`, con la carga anidada bajo `data` y sin un solo campo `default`—, incompatible con `contratos/v1/cmd_trabajo.py`, que ya traía `trabajo_id`. La migración fue reemplazar el contrato local por el real y ajustar la traducción del consumidor de `valor.data.campo` a `valor.campo` (records planos).

**La idempotencia vive en el handler, no en el broker.** `CrearTrabajoHandler` consulta `RepositorioTrabajos.obtener_por_id(trabajo_id)` antes de construir la agregación: si ya existe, devuelve su id sin volver a publicar `TrabajoCreado`. Es la misma forma que ya usa Acreditación para sus comandos repetidos (`ACR-3`) y Emparejamiento para `EmparejarTrabajo` (`EMP-3`) — el patrón se repite porque el problema es el mismo: entrega al-menos-una-vez, handler responsable de no duplicar.

### El adaptador en memoria es por PROCESO, no por sistema

`RepositorioTrabajosMemoria` guarda un diccionario de clase, compartido entre instancias **dentro del mismo proceso**. Con gunicorn en más de un worker, un `POST` y el `GET` que lo verifica pueden caer en workers distintos con diccionarios distintos — el escenario fallaría por una razón que no tiene nada que ver con la arquitectura, la misma clase de trampa que ya documentaron `CON-1` e `INF-4` con otras pruebas. La corrección no es hacer el adaptador más elaborado (eso lo convertiría en algo que nadie usaría en producción): es que `mod-1.sh` fuerza `WORKERS=1` mientras dura la demostración, y lo dice en el propio `docker-compose.yml`.

### El sidecar de reglas regionales vivía dentro de la imagen — MOD-2 no era real

`reglas_regionales.json` se copiaba a la imagen con `COPY src/` del Dockerfile. Bajo esa configuración, "agregar un país" habría exigido reconstruir la imagen — contradice la medida exacta que CA-M2 pide (0 archivos de código cambiados). Se externalizó a `infra/sidecar/reglas_regionales.json`, montado como volumen de solo lectura en `gestion-trabajos` y `gestion-trabajos-consumidor`, con `RUTA_REGLAS_REGIONALES` apuntando ahí. El archivo que queda dentro del servicio (`.../infraestructura/reglas_regionales.json`) sigue siendo el valor por defecto para quien lo corra fuera de Compose (por ejemplo, `pytest`).

**`mod-2.sh` agrega Chile, no Perú.** La colección de Postman ya tiene un caso que depende de que Perú **no** esté configurado (cae al contrato `_default`, es la prueba de la brecha por defecto del sidecar). Agregar Perú en la demostración de MOD-2 habría invalidado esa prueba en lugar de sumarse a ella — un conflicto entre dos partes de la misma entrega que solo aparece si se mira la colección completa, no cada escenario por separado.

### `mod-3.sh` se niega a correr sobre cambios sin comitear

El escenario parchea `objetos_valor.py` en caliente y lo revierte con `git checkout` al final. Si alguien ya tenía cambios sin comitear en ese archivo —trabajando en otra cosa, por ejemplo—, un `git checkout` a ciegas se los borraría. El script comprueba `git diff --quiet` sobre el archivo exacto antes de tocar nada y aborta si no está limpio: es el mismo principio de "antes de sobrescribir, mirar qué hay" que vale para cualquier automatización que edita el árbol de trabajo de otra persona.

### `esquemas.py` importa el contrato real, no lo copia

A diferencia de `spike_esquemas.py` (clases de usar y tirar, preguntas genéricas), `escenarios/esquemas.py` importa `contratos.v1.cmd_trabajo.ComandoCrearTrabajo` para la versión "nueva" de CA-E1: si alguien cambia el contrato real, este script evoluciona con él en vez de quedar demostrando una versión vieja. Solo la versión "vieja" (sin `trabajo_id`) y la versión "incompatible" (con `trabajo_id: Long`) se declaran ad hoc, porque esas dos no existen en ningún lado del código real — son, a propósito, los dos puntos de comparación.

### Verificación ejecutada

Sin Docker ni credenciales de AWS en este entorno: lo verificable sin ellos se verificó; lo que necesita un clúster o una instancia real queda anotado como pendiente, no como hecho.

| Comprobación | Resultado |
|---|---|
| `pytest` de `gestion_trabajos` (Python 3.11.16, instalado con `uv`) | **12 / 12** — incluye `test_aplicacion_trabajos.py` (GT-4, GT-6), nueva |
| Regresión de los otros tres servicios | `operaciones` 20/20 · `emparejamiento` 16/16 · `acreditacion` 19/19 — sin cambios de comportamiento |
| `tests/conftest.py` agregado a `gestion_trabajos` | La suite pasó de ~60 s a 0,4 s (antes, cada prueba esperaba el timeout de un broker inexistente) |
| `docker-compose.yml` (variables y volúmenes nuevos) | YAML válido |
| `escenarios/mod-1.sh`, `mod-2.sh`, `mod-3.sh`, `esquemas.py` | Sintaxis verificada (`bash -n`, `py_compile`); las clases de esquema de `esquemas.py` se instanciaron sin broker y tienen los campos esperados |
| `infra/aws/user-data.sh` | Sintaxis verificada; **no** se aprovisionó una EC2 real |

**Pendiente, en cuanto alguien tenga Docker y (para DEP-1) credenciales de AWS a mano:** correr `mod-1.sh`, `mod-2.sh`, `mod-3.sh` y `esquemas.py` contra un clúster real, y ejecutar el aprovisionamiento de `infra/aws/user-data.sh` sobre una instancia EC2.

---

## ESC-6 · Simplificación tras GT-3 — un solo generador, no dos caminos en paralelo

**Fecha:** 2026-09-14 · **Ejecutado por:** Stiven Cardona · **Dónde:** `herramientas/generador_carga.py`, `escenarios/escenario-6.sh`

Con GT-3 fusionado (ver la sección "GT-3 · Los eventos cruzan entre servicios por primera vez" arriba), Gestión de Trabajos ya publica el `TrabajoCreado`/`EstadoTrabajoCambiado` real en `evt-trabajo-{región}`. El atajo que `escenario-6.sh` usaba —lanzar `generador_carga.py` dos veces en paralelo, una vía HTTP contra GT y otra publicando eventos sintéticos directo en Pulsar— dejó de ser necesario: existía únicamente porque GT no llegaba hasta el stream que Operaciones consume.

**Qué cambió:**

1. `generador_carga.py --via-http` ahora acepta `--con-cambios-estado`: tras el `POST /trabajos`, hace `PUT /trabajos/{id}/estado` con `EMPAREJANDO` (transición válida desde `CREADO`). Antes esa bandera solo tenía efecto en el modo `--topico evt-trabajo-*`.
2. `escenario-6.sh` pasó de dos procesos en paralelo (`pid_http`, `pid_evt`) a una sola llamada. Se cae la sección de "dos caminos" de la cabecera del script y la nota extensa sobre GT-3/GT-4 pendientes.
3. El modo de publicación sintética (`--topico evt-trabajo-*`) **no se elimina**: sigue siendo el correcto para `escenario-8.sh`, que necesita precargar un backlog de eventos sin que exista un `Trabajo` real en la base de GT (el propósito ahí es medir el drenaje del consumidor, no probar la creación).

**Por qué importa para la sustentación:** es un ejemplo concreto de que las herramientas de esta entrega no son un compromiso permanente — el atajo se documentó como temporal cuando se escribió (`docs/decisiones.md`, sección OPS-1…4) y se retiró en cuanto la pieza que lo hacía necesario (GT-3) llegó, sin que nadie tuviera que acordarse de revisarlo por fuera del proceso normal de lectura de este documento.

### Verificación ejecutada

| Comprobación | Resultado |
|---|---|
| `generador_carga.py --via-http ... --con-cambios-estado` contra un puerto cerrado | Reporta la falla de conexión correctamente (`FALLA`, código de salida 1) — el POST y el PUT subsiguiente fallan igual de explícito |
| `escenarios/escenario-6.sh` | `bash -n` (sintaxis) — **no** se corrió contra un clúster real: sigue sin haber Docker en este entorno |

**Sigue pendiente** (igual que antes de esta simplificación): correr `escenario-6.sh` de punta a punta contra el sistema real y confirmar los seis criterios de aceptación.

---

## US-02 · BFF y trazabilidad por petición

**Fecha:** 2026-09-20 · **Verificable con:** `python herramientas/verificar_aislamiento.py`, `bash escenarios/bff.sh` y `newman run postman/hogar-alpes-bff.postman_collection.json -e postman/bff-local.postman_environment.json`

Especificación y diseño: `specs/001-bff-entry-point/`. Se recomienda enmendar el Principio I de la Constitución (versión MINOR) para nombrar al *componente de borde*, en un PR aparte; mientras tanto, las excepciones de abajo quedan justificadas por escrito, como exige la Gobernanza.

### 1 · El BFF es un componente de borde, y eso exige dos excepciones escritas al Principio I

`servicios/bff/` no es un servicio de dominio: no tiene base de datos, no habla con Pulsar y no guarda estado. Su trabajo es justamente hacer llamadas HTTP hacia adentro, y eso contradice la frase general «ningún servicio llama a otro por HTTP». Excepciones:

| Excepción | Por qué es necesaria | Alternativa descartada |
|---|---|---|
| **El BFF hace HTTP hacia los servicios** | Un punto de entrada único y las consultas compuestas exigen llamadas síncronas hacia adentro. El propio código lo evitó antes: `GET /trabajos/{id}/seguimiento` se retiró de Gestión de Trabajos (GT-5) porque habría sido una llamada GT → OPS | *Que el BFF lea de una proyección alimentada por eventos*: obliga a darle base de datos y consumidor, justo lo que la historia prohíbe, y duplica la lógica de cada servicio. *No hacer compuestos*: es un simple *gateway* y no cumple el objetivo |
| **La API de cada servicio comparte una red `red-bff-<svc>` con el BFF** (el Principio I dice «comparte red únicamente con el broker y con su propia base») | El BFF debe alcanzar la API de cada servicio. Una red por par (BFF + un solo servicio) evita que el BFF comparta red con el broker o con las bases | *Poner al BFF en `red-broker`*: lo acercaría al broker y a todos los servicios. *Sin redes por par*: el BFF no tendría ruta a los servicios |

Los cinco servicios de dominio siguen sin poder hablarse entre sí. Ningún servicio adquiere un cliente HTTP ni una variable de entorno hacia otro servicio o hacia el BFF.

### 2 · «No alcanzarse entre sí» significa no llamarse, no aislar la red

La historia proponía comprobar que, desde un servicio, el nombre de otro no resuelve. **Esa comprobación no puede pasar y nunca pudo**: las API y los consumidores comparten `red-broker` y se resuelven por nombre (comprobado con Docker el 2026-09-19). El equipo aclaró que la regla del proyecto es *no comunicarse de forma síncrona*; compartir una red es aceptable. Por eso:

- La topología existente **no se toca**.
- La regla se verifica sobre el código y la configuración: `herramientas/verificar_aislamiento.py` (solo lectura) comprueba que ningún servicio de dominio tiene cliente HTTP ni literales `http(s)://`, que ninguna variable de entorno apunta a otro servicio o al BFF, que solo el BFF tiene variables `URL_*`, que cada `red-bff-*` tiene exactamente al BFF y a un servicio, y que el BFF no declara volúmenes, `DATABASE_URI`, `BROKER_HOST` ni `depends_on`.
- Se corrigió `docs/hoja-verificacion-infraestructura.md` §6, que mostraba una llamada HTTP entre servicios con el comentario «falla: no comparten red». Era incorrecto. Se conservan las dos comprobaciones de bases de datos (`getent hosts postgres-<ajena>`), que sí son aislamiento de red.

**Verificado (2026-09-20):** el verificador dio PASA en todos sus criterios (PENDIENTE solo para `red-bff-saga`, que tiene únicamente al BFF hasta que exista `saga-log`). Además se comprobó que **falla cuando debe**: se introdujo a propósito un `urllib`/`http://` en un servicio, una mención del BFF en un módulo de dominio, una copia divergente de `correlacion.py`, una variable de entorno hacia otro servicio, una tercera pertenencia a una red `red-bff-*` y un `depends_on` del BFF; el script reportó FALLA en cada caso (y se restauró todo). Con el sistema levantado: `docker compose exec bff getent hosts broker-1` y `... postgres-trabajos` terminan con código 2 (no resuelven), y `gestion-trabajos → postgres-acreditacion` también.

### 3 · El identificador de correlación viaja por el borde, no por el dominio

Un `ContextVar` (`seedwork/infraestructura/correlacion.py`) se fija al entrar —cabecera `X-Correlation-Id` de una petición HTTP o campo/propiedad del mensaje consumido— y lo leen tres lugares: el despachador (propiedades del mensaje), los mapeadores (campo del sobre, vía `correlacion.actual()`) y una fábrica de registros de `logging` (`cid=` en cada línea). Es posible sin pasarlo por el dominio porque la Unidad de Trabajo despacha los eventos de integración de forma síncrona en el mismo hilo que atendió la petición o el mensaje.

- El archivo es **idéntico byte a byte** en seis copias (plantilla, cuatro servicios y BFF), por `TO-7`; el verificador lo comprueba por SHA-256.
- Ningún comando, evento de dominio, entidad ni tabla gana un campo; el verificador comprueba que `correlation`/`correlacion` no aparece en `dominio/` ni en ningún `dto.py`.
- **No es la clave de partición.** La clave sigue siendo el `trabajo_id` (`proveedor_id` en Acreditación) y viaja como argumento `partition_key`; el identificador viaja en el sobre y en las propiedades, que Pulsar no usa para enrutar. `contratos/` y `sobre()` no cambian (los `schema/v1/mensajes.py` siguen idénticos a `contratos/v1/mensajes.py`).
- Regla general: si llega una petición o un mensaje sin identificador válido (forma `[A-Za-z0-9._:-]{1,64}`), quien lo recibe crea uno. **Consecuencia observada:** un mensaje sin identificador consumido por dos suscripciones queda con dos identificadores distintos, uno por receptor; cada uno lo propaga desde ahí.
- Para seguir **la vida de un trabajo** entre peticiones (cada petición tiene su propio `cid=`), las líneas de registro que tocan un trabajo llevan además `trabajo_id=<id>` (campos de registro genéricos: el módulo no nombra ningún dominio, cada servicio pasa el nombre del campo). En Operaciones y Emparejamiento el argumento de ruta se llama `trabajo_id`, no `id`, y `campos_ruta` debe llamarse así o no escribe nada.

**Verificado (2026-09-20, sistema real):** una sola búsqueda del `correlation_id` devuelto por `POST /trabajos` recorre `bff`, `gestion-trabajos`, `operaciones-consumidor` y `emparejamiento-andina` en orden de marca de tiempo; el mismo valor está en las propiedades **y** en el sobre Avro de un mensaje real de `evt-trabajo-andina`, `evt-emparejamiento` y `evt-acreditacion`; los tres mensajes de un trabajo (creación y dos cambios de estado) cayeron en **una sola** partición de `evt-trabajo-andina`; una llamada directa a Gestión de Trabajos sin cabecera quedó identificada; un mensaje publicado sin `correlation_id` quedó identificado por Operaciones y por Emparejamiento, y el que Emparejamiento publicó después lleva el suyo.

### 4 · `502` cuando un servicio responde `5xx`

La historia solo prevé `503` (no responde). Si un servicio responde con un error interno, el BFF **no reenvía su cuerpo** (podría ser una página HTML o una traza) y responde `502` con `servicio` y `status_upstream`. Se separa de `503` porque se diagnostican distinto: «no responde» frente a «responde mal».

### 5 · Puerto `8090`

La historia propone `8080`, que ya publica `broker-1`. El BFF usa `${PUERTO_BFF:-8090}`. Se registró la regla de entrada del puerto en `infra/aws/terraform/main.tf` (`terraform validate` correcto; `terraform apply` no se ejecutó).

### 6 · `{id}` de `/proveedores/{id}/completo` es el id de la acreditación

`GET /acreditaciones/{id}` busca por el id de la acreditación, no por `proveedor_id` (son UUID distintos). La respuesta incluye `proveedor_id`.

### 7 · La primera petición de la colección de la Entrega 4 es la única excepción a «solo cambiar la dirección»

`GET /health` de esa colección afirma `service == 'gestion-trabajos'`. El BFF responde con el **suyo** (necesario para balanceadores y Kubernetes), así que esa petición se excluye. Todas las demás carpetas corren contra el BFF cambiando solo la dirección base: **17 peticiones, 35 aserciones, 0 fallos** (2026-09-20), incluidas las que esperan que Operaciones abra el seguimiento por Pulsar. Esa colección solo cubre Trabajos y Operaciones, así que la fidelidad del reenvío de Acreditación y Emparejamiento la prueban `tests/test_reenvio.py` y las carpetas 2 y 3 de la colección nueva.

### 8 · El BFF no nace de copiar toda la plantilla (Principio III)

La plantilla trae seedwork de dominio, SQLAlchemy, Pulsar y un proceso consumidor; el BFF no puede tener nada de eso. Se parte de su esqueleto (`Dockerfile`, fábrica, `/health`, `pytest.ini`) y solo se copia `correlacion.py`.

### 9 · `correlation_id` deja de ser `trabajo_id`/`proveedor_id` y pasa a ser un identificador por petición, **sin** `-v2`

`RS-4` exige un stream nuevo ante un «cambio de significado». No aplica: el campo conserva su tipo y su función (correlacionar, `TO-4`), su definición no cambia (`String(default=None, required_default=True)`) y ningún consumidor depende de que valga el id del trabajo.

**Evidencia** (`grep -rn "correlation_id" servicios/ escenarios/ herramientas/ contratos/`, 2026-09-20): todas las coincidencias son definiciones del campo en los contratos, escrituras (`sobre(...)`, mapeadores, despachadores), el formato de registro, herramientas que **publican** con él (`generador_carga.py`, `cargar_acreditaciones.py`, `esquemas.py`) o un `print` de depuración en `verificar_contratos.py`. **Ningún código de negocio lo lee.**

**Costo aceptado:** el ciclo de vida de un trabajo ya no comparte un único identificador entre peticiones; cada petición abre su propia cadena. Se mitiga con `trabajo_id=` en los registros (punto 3).

**Restricción para US-01:** la saga **no** debe usar `correlation_id` como clave del trabajo; usa `trabajo_id`. Un servicio nuevo debe nacer de la plantilla ya actualizada y declarar su `campos_ruta`.

### Hallazgos de la implementación que conviene dejar dicho

- **El tiempo límite no cubría la resolución del nombre.** Con `saga-log` inexistente, `getaddrinfo` tardaba 4–8 s en Docker (el DNS interno reenvía hacia afuera el nombre que no conoce) y `GET /estado-del-sistema` respondía en ~8 s pese a `TIMEOUT_COMPUESTO_S=1.5`. Se acotó la resolución con un hilo por llamada: ahora el compuesto responde en ~1.5 s y hay pruebas (`test_un_dns_lento_no_pasa_del_tiempo_limite_*`). Afecta también a un servicio detenido, cuyo nombre deja de resolver.
- **En Windows, `infra/pulsar/*.sh` se descargan con CRLF** (por `core.autocrlf`) y `pulsar-config` falla dentro del contenedor (`$'\r': command not found`), por lo que nunca se crean el *tenant*, los *namespaces* ni los tópicos y los servicios publican con `TopicNotFound`. No es de esta entrega, pero bloquea un arranque en frío en esa plataforma. Se resolvió a mano ejecutando el script sobre una copia sin `\r`; conviene fijar `*.sh text eol=lf` en un `.gitattributes`.
- **`herramientas/verificar_contratos.py`** verifica bien la parte estructural (regla de INF-0, sobre completo) pero su ida y vuelta usa tópicos ad hoc de `public/default`, y estos brokers tienen `allowAutoTopicCreation: false`: da `TopicNotFound`. No lo causa este cambio (`contratos/` no se tocó) y queda pendiente.
- En Windows, conectar a un puerto cerrado tarda ~2 s en fallar con «rechazada»; las pruebas del BFF usan un tiempo límite por defecto de 3 s para no confundirlo con un `TIMEOUT`.

### Verificación ejecutada (2026-09-20)

| Qué | Resultado |
|---|---|
| `pytest` `servicios/bff` | 110 pruebas en verde (servidores HTTP falsos reales; sin base de datos ni Pulsar) |
| `pytest` `gestion_trabajos` · `operaciones` · `acreditacion` · `emparejamiento` | 68 · 31 · 31 · 32 en verde (antes: 12 · 20 · 19 · 16) |
| `python herramientas/verificar_aislamiento.py` | PASA en todos; PENDIENTE solo `red-bff-saga` |
| `bash escenarios/bff.sh` (secciones US1, US2, US3) | Sin fallos; PENDIENTE lo que depende de `saga-log` |
| `newman` de la Entrega 4 contra el BFF | 17 peticiones, 35 aserciones, 0 fallos |
| `newman` de la colección del BFF (carpetas 0–6, 8, 9) | 42 peticiones, 97 aserciones, 0 fallos; con `sagasDisponibles=true` la carpeta de sagas se pone en rojo, como debe |
| `terraform validate` | Correcto |
| Regresión de la Entrega 4 (la publicación y el consumo de todos los servicios cambiaron) | `escenario-6`: backlog creciente, 350/350 seguimientos, 0 duplicados, 0 huérfanos y suscripciones aisladas en PASA; p95 de `POST /trabajos` 185 ms con el consumidor detenido frente a 173 ms de línea base y 0 % de errores (medido aparte: la medición del propio script no pudo leerse por rutas MSYS en Windows). `escenario-8` reducido: CA-8.1, 8.2 y 8.3 PASA; CA-8.4 no verificable aquí (`agregar-region.sh` viene con CRLF). `mod-2` y `mod-3` PASA. `mod-1.sh` FALLA por dos supuestos previos a esta entrega (un commit histórico y una carpeta de Postman que no corre); a mano, el adaptador en memoria pasa los escenarios 2 y 3 (28 aserciones, 0 fallos). `esquemas.py` y `verificar_contratos.py` (ida y vuelta): `TopicNotFound` por la creación automática de tópicos desactivada. Ninguno se debe al BFF ni a la correlación |

**Pendiente:** todo lo que depende de US-01 (carpetas 5 y 7 de Postman con `saga-log` real, paso `saga-log` de la búsqueda de una saga, CA-2.25 y CA-2.26); `bff-aws` (requiere desplegar en AWS).

## US-01 · Saga de asignación de un trabajo (Entrega 5)

Implementación completa según `specs/002-saga-asignacion-trabajo/` (plan, research D1–D10, data-model, contratos, tasks). Tres decisiones tomadas durante la implementación que no estaban cerradas en el plan técnico:

### 1 · `ConfirmarVigencia` no pasa por la Unidad de Trabajo ni por un evento de dominio

El paso 3 de ida (`vigencia-confirmada`/`vigencia-rechazada`) no muta el agregado `Acreditacion`: es una consulta a la proyección `vigencia_por_proveedor` seguida de una publicación. Se modeló con un objeto `DecisionVigencia` (no un `EventoDominio`) que implementa la misma interfaz que consume `Despachador.publicar_evento` (`MapeadorVigenciaIntegracion.entidad_a_dto`), para reutilizar el mecanismo existente de publicación (y su mock en pruebas) sin forzar una mutación de agregado que no existe.

### 2 · `saga_log`: se retiró `seedwork/infraestructura/despachadores.py` de la copia

CA-1.16 exige que `saga_log` no publique nada. El despachador copiado de `_plantilla` quedó sin ningún importador (verificado con `grep -rl despachadores servicios/saga_log/`), así que se eliminó — es la instrucción explícita de T057 ("quitar/deshabilitar el despachador copiado de `_plantilla` si quedó sin usar"). `config/broker.py` y `seedwork/infraestructura/uow.py` se dejaron intactos (siguen usando `cliente()` para consumir, y son parte del seedwork que MUST duplicarse byte a byte entre servicios); el `grep -rn "create_producer|publicar_evento" servicios/saga_log/src/` de `quickstart.md` todavía encuentra la *definición* de `productor()` en `config/broker.py` y los nombres de método `publicar_eventos_dominio`/`publicar_eventos_integracion` en `uow.py` — ninguno de los dos se invoca desde el código de negocio de `saga_log`; es una coincidencia de substring del comando documentado, no evidencia de publicación real.

### 3 · Postman, carpeta 7: las aserciones "PENDIENTE hasta US-01" se reescribieron

Las cuatro peticiones de "7 · Saga de punta a punta" comparaban un literal contra una lista de literales (`pm.expect('COMPENSADA').to.be.oneOf(['COMPLETADA', 'COMPENSADA'])`) — nunca leían la respuesta real, y las tres peticiones de fallo no mandaban `simular_fallo` en el cuerpo. Se corrigió el cuerpo de las tres (`simular_fallo: SIN_CANDIDATOS/VIGENCIA/ASIGNACION`) y se reemplazó la aserción vacía por una real sobre la respuesta inmediata (`202` + `seguimiento_saga` presente). Verificar el estado FINAL de la saga requiere sondear con espera, que el sandbox de Postman no garantiza de forma confiable; esa verificación queda en `escenarios/saga.sh` (Principio VI: una prueba que no ejercita el camino real, o que se compara contra sí misma, es peor que no tenerla).

### Verificación ejecutada (2026-09-20, sin Docker disponible en el entorno de implementación)

| Qué | Resultado |
|---|---|
| `pytest` `gestion_trabajos` · `emparejamiento` · `acreditacion` · `saga_log` | 75 · 38 · 33 · 17 en verde |
| `pytest` `operaciones` · `bff` (regresión, sin tocar) | 31 · 110 en verde |
| Simulaciones manuales en proceso (sin broker, sqlite en memoria) de los 4 casos de `quickstart.md` por servicio | Caso 1 (asignación con dos candidatos en competencia), Caso 2 (VIGENCIA), Caso 3 (SIN_CANDIDATOS), Caso 4 (ASIGNACION): los tres servicios producen los pasos y estados finales esperados, incluida la idempotencia ante reentrega (`ConfirmarAsignacion`, `LiberarReserva`) |
| `python -m py_compile herramientas/verificar_contratos.py` | Sintaxis correcta; **no se ejecutó contra un broker real** (`docker` no disponible en este entorno) |
| `bash -n infra/pulsar/inicializar.sh`, `bash -n escenarios/saga.sh` | Sintaxis correcta |
| `python -c "import yaml; yaml.safe_load(...)"` sobre `docker-compose.yml` | YAML válido |

**Pendiente (requiere `docker compose up -d --build` y no se pudo ejecutar en este entorno):** `bash escenarios/saga.sh` contra el sistema real (T062); `newman` de las carpetas 5 y 7 contra el BFF real (T060, la revisión de contenido sí se hizo); regresión completa de `escenarios/escenario-6.sh`, `escenario-8.sh`, `mod-1.sh`/`mod-2.sh`/`mod-3.sh` (T061); `herramientas/verificar_contratos.py` contra un clúster Pulsar real (los dos contratos extendidos, T005).
