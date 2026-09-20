# Entrega 5 · Historias de usuario

Tres historias, una por cada actividad de la entrega.

| # | Historia | De qué trata |
|---|---|---|
| [US-01](US-01-saga-asignacion-de-trabajo.md) | **Saga de asignación de un trabajo** | Completar la transacción larga que la Entrega 4 dejó a la mitad, con sus reversiones, y un registro que permita ver en qué va cada transacción |
| [US-02](US-02-bff.md) | **BFF — un solo punto de entrada** | Un servicio nuevo en Python que reúne las APIs de los cinco servicios detrás de una sola dirección, más una colección de Postman para probarlo |
| [US-03](US-03-despliegue-kubernetes-aws.md) | **Despliegue en Kubernetes sobre AWS** | Agregar la opción de desplegar todo el sistema en un clúster de Kubernetes en AWS, sin perder el despliegue actual con Docker Compose |

> El número de cada historia es un **identificador, no un orden de ejecución**.
> El orden recomendado para construirlas —que empieza por el BFF— está en
> [Orden de ejecución recomendado](#orden-de-ejecución-recomendado).

---

## Punto de partida: qué dejó lista la Entrega 4

Cuatro microservicios corriendo, cada uno con su base de datos, que se hablan
**únicamente** por mensajes sobre Apache Pulsar:

| Servicio | Qué hace | Dirección local |
|---|---|---|
| `gestion_trabajos` | Registra las solicitudes de trabajo y administra su ciclo de vida | `:8000` |
| `operaciones` | Le hace seguimiento a cada trabajo (prioridad y tiempo límite) | `:8001` |
| `acreditacion` | Guarda el historial completo de certificación de cada proveedor | `:8002` |
| `emparejamiento` | Busca proveedores certificados y disponibles para un trabajo | `:8003` |

Y cinco canales de mensajes (tópicos) ya creados y en uso:

| Tópico | Quién publica | Quién escucha hoy |
|---|---|---|
| `cmd-trabajo-{región}` | Clientes / generador de carga | Gestión de Trabajos |
| `evt-trabajo-{región}` | Gestión de Trabajos | Operaciones · Emparejamiento |
| `cmd-acreditacion` | Clientes / carga inicial | Acreditación |
| `evt-acreditacion` | Acreditación | Emparejamiento (su proyección de proveedores) |
| `evt-emparejamiento` | Emparejamiento | **nadie todavía** |

Esa última fila es la clave de esta entrega: Emparejamiento ya publica el
resultado de su búsqueda, y el propio código dice que ese evento *«lo escuchará
la saga de la Entrega 5»*. La pieza que falta no es nueva: es la continuación
de algo que se dejó preparado a propósito.

---

## Cómo se eligieron las transacciones de la SAGA

La especificación de la Entrega 4 (`docs/01-especificacion.md`, §4.5) ya había
identificado la transacción larga de referencia y había marcado explícitamente
cuáles pasos quedaban para la Entrega 5. Aun así, se compararon cuatro
candidatas antes de confirmarla:

| Candidata | Servicios que involucra | Por qué sí / por qué no |
|---|---|---|
| **A · Asignación de un trabajo**<br>crear → buscar candidatos → verificar vigencia → asignar | GT · EMP · ACR (+ Operaciones como testigo) | ✅ **Elegida.** Es la única que involucra tres servicios que *ya se oyen* entre sí; usa los tres tópicos de eventos que ya existen; cada paso tiene una reversión con sentido de negocio evidente (cancelar el trabajo, liberar al proveedor reservado); y cierra un riesgo que la Entrega 4 dejó abierto a propósito: que a un proveedor cuya acreditación acaba de vencer se le siga asignando trabajo |
| B · Alta y acreditación de un proveedor | ACR · EMP | ❌ Solo dos servicios, y ya funciona completa hoy. No hay nada que compensar: si algo falla, simplemente no se acredita |
| C · Cierre y verificación de calidad de un trabajo | GT · OPS | ❌ Operaciones no publica ningún evento hoy: habría que convertirlo en productor y crear un tópico nuevo, justo lo que se quiere evitar |
| D · Revocación de una acreditación con trabajos ya asignados | ACR · EMP · GT | ⚠️ Muy buena candidata, y es el reverso natural de la A — pero **depende de que la A exista primero** (no se puede desasignar lo que nunca se asignó). Queda anotada como extensión natural, no como el alcance de esta entrega |

**Conclusión:** la saga es la candidata A, *«Asignación de un trabajo»*, con
cuatro pasos y tres reversiones. El detalle completo está en
[US-01](US-01-saga-asignacion-de-trabajo.md).

---

## Decisiones tomadas y aprobadas antes de escribir las historias

| # | Decisión | Qué se decidió | Por qué |
|---|---|---|---|
| D5-1 | **Patrón: coreografía, no orquestación** | Cada servicio reacciona por su cuenta a lo que publican los demás y publica su reversión en el mismo tópico que ya usa, con un tipo de evento distinto | Un orquestador obligaría a crear canales de comando nuevos hacia Emparejamiento y Acreditación —justo lo que se quiere evitar. Con cuatro pasos, la coreografía sigue siendo manejable, y el registro de sagas resuelve su único problema real: la falta de visibilidad |
| D5-2 | **Cero tópicos nuevos** | Las reversiones viajan por los mismos tópicos, distinguidas por el campo `type` del mensaje | Mantiene garantizado el **orden** entre un paso y su reversión: dos mensajes en tópicos distintos no tienen orden entre sí |
| D5-3 | **El registro de sagas es un servicio nuevo** (`saga-log`) | Un quinto microservicio, que solo escucha y anota. No decide nada ni publica nada | Separa con claridad *«quién ejecuta la saga»* de *«quién la observa»*. |
| D5-4 | **El BFF reenvía y además compone** | Expone todos los endpoints de los servicios bajo una sola dirección, y agrega endpoints que resuelven en una llamada lo que hoy son tres o cuatro | Un simple reenviador sería un *gateway*, no un BFF. Lo que justifica el nombre es ahorrarle al cliente las llamadas múltiples |
| D5-5 | **Kubernetes: todo dentro del clúster** | Los cinco microservicios, el BFF, las cinco bases de datos y el clúster de Pulsar corren dentro de EKS | Es el *«ambiente de producción real»* que pide la actividad, y mantiene el requisito de que el equipo configure y despliegue su propio clúster de Pulsar en vez de contratar uno gestionado |
| D5-6 | **El despliegue con Docker Compose no se retira** | Kubernetes es una **opción adicional**, no un reemplazo | Todas las pruebas y los escenarios de calidad de la Entrega 4 corren hoy sobre Compose. Perder ese camino sería perder la evidencia ya producida |
| D5-7 | **El identificador de correlación lo crea el BFF** | El BFF genera un código único por petición; todos los servicios lo copian sin modificarlo en cada mensaje que publican y en cada línea de registro | Es la puerta por donde entra todo y el único punto donde una petición todavía es una sola cosa antes de repartirse. Hoy cada servicio se inventa el suyo —Gestión de Trabajos y Emparejamiento usan el del trabajo, Acreditación el del proveedor—, así que **no se puede seguir una petición de punta a punta**. Definido en US-02, verificado sobre la saga en US-01 |
| D5-8 | **La clave de partición no se toca** | Los eventos de trabajo se siguen particionando por el identificador del trabajo | Verificado en el código: la clave de partición y el identificador de correlación son dos argumentos distintos del despachador, y Pulsar solo enruta por el primero. D5-7 no tiene ningún efecto sobre el orden ni sobre las particiones |

---

## Cómo encajan las tres historias

**Los números US-01, US-02 y US-03 son nombres, no un cronograma.** El orden en
que se construyen es otro, y va abajo.

### Lo que cada historia necesita de las demás

```
        ┌─────────────────────────────────────────────┐
        │  PREVIO · La regla del identificador de     │
        │  correlación (D5-7): quién lo crea, cómo    │
        │  viaja, cómo se escribe en los registros    │
        └───────────────┬─────────────────────────────┘
                        │  la necesitan las dos
            ┌───────────┴───────────┐
            ▼                       ▼
     US-02 (BFF)              US-01 (saga + saga-log)
            │                       │
            │  el BFF gana las rutas de saga
            │  y su parte del endpoint compuesto
            └───────────┬───────────┘
                        ▼
              US-03 (Kubernetes)
        despliega los 7 componentes que
        existan cuando le toque
```

Son **tres dependencias estrechas**, no tres historias encadenadas:

| Quién necesita qué | De quién | Se resuelve con |
|---|---|---|
| La regla del identificador de correlación | Trabajo previo compartido | Un acuerdo escrito antes de empezar, no una historia terminada |
| Las rutas `/sagas/*` y la parte de saga del endpoint compuesto | US-01 → US-02 | Acordar los tres endpoints del registro de sagas el primer día; el BFF los enchufa cuando existan |
| El inventario de componentes a desplegar | US-01 y US-02 → US-03 | Ya está en esta página: son siete |

### Orden de ejecución recomendado

| Orden | Qué | Por qué en ese momento |
|---|---|---|
| **0** | **La regla del identificador de correlación**, acordada y escrita | Es lo único que las otras dos comparten de verdad. Es un acuerdo de media hora, no una historia. Mismo patrón que `CON-1` en la Entrega 4: se definió aparte *para desbloquear el paralelismo*, no porque fuera un entregable en sí |
| **1** | **US-02, el BFF** — primero en terminar | Es la pieza de **menor riesgo**: sin base de datos, sin broker, sin cambios de contrato, sin incógnitas técnicas. Y es la puerta contra la que se van a escribir todas las demostraciones posteriores: si llega después, la prueba de punta a punta de la saga se escribe **dos veces** —una contra los servicios sueltos y otra contra el BFF |
| **1 (en paralelo)** | **US-01, la saga** — primera en empezar | Es la pieza de **mayor riesgo y mayor peso** en la entrega. Lo riesgoso arranca temprano, para que si algo sale mal quede tiempo de reaccionar. Que el BFF termine antes no significa que la saga empiece después |
| **2** | **US-03, Kubernetes** | Necesita que los siete componentes existan para desplegarlos. Su parte más riesgosa —el almacenamiento durable de la mensajería— **sí se puede atacar antes**, y conviene: ver su propio orden de trabajo interno |

**En una frase:** el BFF es el primero en *terminar*; la saga es la primera en
*empezar*. No son lo mismo, y con tres personas trabajando en paralelo —la
convención del proyecto es una rama y un *pull request* por persona— las dos
cosas caben a la vez.

### Por qué esto no serializa nada

Mientras el BFF no exista, **cada servicio genera el identificador de
correlación si la petición o el mensaje que recibe no lo trae**. Esa regla no es
un parche temporal: se queda para siempre, porque las APIs de los servicios
siguen abiertas y el generador de carga publica directo en los tópicos. El día
que el BFF aparece, lo único que cambia es que pasa a haber un **único creador**
para el camino normal. Nada que se haya escrito antes hay que rehacerlo.

---

## Hallazgos del código que estas historias tienen que resolver

Dos cosas que se encontraron al revisar el repositorio y que **no son opcionales**
si las historias se van a cumplir:

1. **El identificador de correlación no es consistente, y nadie es su dueño.**
   Gestión de Trabajos y Emparejamiento marcan cada mensaje con el identificador
   del trabajo, pero Acreditación lo marca con el del proveedor
   (`servicios/acreditacion/.../aplicacion/handlers.py:28`). Tal como está hoy,
   ni el registro de sagas ni una persona leyendo los registros pueden unir los
   pasos de una misma petición. Se corrige dándole el dueño que le falta: **el
   BFF lo crea y todos lo propagan** (decisión D5-7, definida en US-02 y
   verificada sobre la saga en US-01).

   **Comprobado que no afecta el particionado:** en
   `seedwork/infraestructura/despachadores.py` la clave de partición y las
   propiedades del mensaje se pasan como dos argumentos separados, y en
   `modulos/trabajos/aplicacion/handlers.py` la clave se fija explícitamente al
   identificador del trabajo. Pulsar enruta por la clave, nunca por las
   propiedades ni por el sobre. Tampoco es un cambio de contrato: el campo
   `correlation_id` ya existe en los cinco contratos con su valor por defecto.
2. **Un tópico solo admite una forma de mensaje.** Para que la respuesta de
   Acreditación pueda viajar por el tópico que ya existe, ese mensaje tiene que
   ganar un campo nuevo (el identificador del trabajo). Es un cambio
   *compatible* —el mecanismo ya está probado en la Entrega 4— pero hay que
   hacerlo a propósito y verificar que los consumidores actuales no se rompan.
