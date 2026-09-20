# US-02 · BFF: un solo punto de entrada para todas las funcionalidades

| Campo | Valor |
|---|---|
| **Entrega** | 5 |
| **Actividad del enunciado** | (b) API tipo BFF + colección de Postman |
| **Servicio nuevo** | `bff` — sin base de datos, sin conexión al broker |
| **Tecnologías** | Las mismas del proyecto: Python 3.11, Flask, gunicorn. **Ningún framework nuevo** |
| **Puerto propuesto** | `8080` |
| **Responsabilidad adicional** | Es quien **crea** el identificador de correlación que el resto del sistema propaga |
| **Estado** | Propuesta — pendiente de aprobación |

---

## La historia

> **Como** persona que usa o prueba el sistema —una aplicación cliente, alguien
> del equipo,
> **quiero** poder hacer todas las peticiones contra **una sola dirección**, en
> lugar de tener que saber en qué puerto vive cada microservicio,
> **para** usar el sistema sin necesitar conocer cómo está dividido por dentro.
>
> **Y quiero** que las consultas que hoy exigen tres o cuatro llamadas separadas
> se puedan resolver con una sola,
> **para** no tener que armar a mano, del lado del cliente, la respuesta completa
> a una pregunta simple como *«¿cómo va este trabajo?»*.
>
> **Y como** persona que tiene que diagnosticar un problema,
> **quiero** que cada petición que entra reciba un código único que todos los
> servicios copien en sus registros,
> **para** poder reconstruir lo que pasó con una sola búsqueda, en lugar de leer
> los registros de seis servicios tratando de adivinar qué línea corresponde a
> qué petición.

---

## Por qué esta historia existe

Hoy, para responder *«¿cómo va el trabajo X?»* hay que hacer cuatro llamadas a
cuatro direcciones distintas:

```
GET  localhost:8000/trabajos/X              ¿en qué estado está?
GET  localhost:8001/seguimientos/X          ¿qué prioridad y plazo tiene?
GET  localhost:8003/emparejamientos/X       ¿qué candidatos se le encontraron?
GET  localhost:8004/sagas/X                 ¿su asignación terminó bien?
```

Eso obliga a cualquier cliente a conocer la división interna del sistema, y lo
ata a ella: el día que un servicio se parta en dos, todos los clientes se
enteran. El BFF pone una capa delante que absorbe esa estructura:

```
GET  localhost:8080/trabajos/X/completo     todo lo anterior, en una respuesta
```

---

## Qué se construye

Un microservicio nuevo, `servicios/bff/`, con la misma estructura de carpetas,
el mismo Dockerfile y las mismas versiones de librerías que los demás. Con dos
diferencias importantes respecto a sus hermanos:

- **No tiene base de datos.** No guarda nada.
- **No se conecta al broker.** No publica ni consume mensajes.

Es decir: no es un microservicio de dominio, es un **componente de borde**. Esa
distinción importa y hay que poder defenderla, porque el proyecto tiene una
regla que dice que ningún servicio llama a otro por HTTP. El BFF **no es un
servicio de dominio**: es la puerta por la que entran los clientes, y su trabajo
es precisamente hacer llamadas HTTP hacia adentro. Los cinco servicios de
dominio siguen sin poder hablarse entre sí — eso no cambia.

### Las dos capas del BFF

**1. Reenvío directo.** Cada ruta de los cinco servicios queda disponible bajo
la dirección del BFF, con **exactamente la misma ruta, el mismo cuerpo y el
mismo código de respuesta**. Un `202` sigue siendo `202`; un `400` de una regla
regional sigue siendo `400` con el mismo mensaje.

| Grupo | Rutas | Servicio detrás |
|---|---|---|
| Trabajos | `POST /trabajos` · `GET /trabajos/{id}` · `GET /trabajos?estado=` · `PUT /trabajos/{id}/estado` | Gestión de Trabajos |
| Seguimiento | `GET /seguimientos/{id}` · `GET /seguimientos/conteo` · `GET /eventos-procesados/conteo` | Operaciones |
| Acreditaciones | `POST /acreditaciones` · `PUT /acreditaciones/{id}/aprobar` · `PUT /acreditaciones/{id}/revocar` · `GET /acreditaciones/{id}` · `GET /acreditaciones/{id}/eventos` | Acreditación |
| Emparejamiento | `GET /candidatos` · `GET /emparejamientos/{id}` | Emparejamiento |
| Sagas | `GET /sagas/{id}` · `GET /sagas?estado=` · `GET /sagas/resumen` | Registro de sagas (US-01) |

> **Sobre el orden de construcción.** Esta historia está pensada para
> **terminarse primero**, antes que la saga: es la de menor riesgo y es la puerta
> contra la que se escriben todas las demostraciones posteriores. Si el registro
> de sagas todavía no existe cuando el BFF esté listo, sus tres rutas y la parte
> de saga del endpoint compuesto **llegan en una segunda pasada** — enchufar una
> ruta más al reenvío es trabajo de minutos. Lo único que hay que acordar el
> primer día son los nombres de esos tres endpoints.

**2. Endpoints compuestos.** Cuatro rutas que no existen en ningún servicio y que
solo tienen sentido en el BFF, porque su valor es justamente juntar lo que está
repartido:

| Ruta | Qué devuelve | A cuántas llamadas reemplaza |
|---|---|---|
| `GET /trabajos/{id}/completo` | El trabajo, su seguimiento operativo, su emparejamiento y el estado de su saga | 4 |
| `GET /proveedores/{id}/completo` | La acreditación del proveedor, su historial completo y si hoy aparece como candidato disponible | 3 |
| `GET /estado-del-sistema` | La salud de los seis componentes y el resumen de sagas por estado | 6 |
| `POST /trabajos/asignacion` | Crea el trabajo y devuelve, junto con la confirmación, la dirección donde seguir el avance de su saga | 1 + conveniencia |

Los endpoints compuestos **degradan parcialmente**: si Operaciones no responde,
`GET /trabajos/{id}/completo` devuelve el trabajo, el emparejamiento y la saga,
y marca la parte de seguimiento como *no disponible* en lugar de fallar entera.
Eso es exactamente el comportamiento que el sistema promete —que la caída de un
servicio no tumbe al resto— visible desde el borde.

---

## Cómo se comporta el BFF

| Situación | Qué hace |
|---|---|
| El servicio de atrás responde normal | Devuelve la respuesta tal cual, sin modificar el código ni el cuerpo |
| El servicio de atrás responde un error de negocio (`400`, `404`, `409`) | Lo devuelve igual, sin reinterpretarlo. El BFF **no agrega reglas de negocio** |
| El servicio de atrás no responde o tarda demasiado | Devuelve `503` con un mensaje claro que dice **cuál** servicio no está disponible, y con el identificador de correlación en la cabecera para poder rastrear qué pasó. Nunca un error interno ni una traza |
| La ruta no existe en ningún servicio | `404` con la lista de grupos de rutas disponibles |
| El cliente manda un identificador de correlación | El BFF lo respeta y lo propaga hacia adentro |
| El cliente no lo manda | **El BFF lo crea.** Es su responsabilidad — ver la sección siguiente |

**Tres cosas que el BFF NO hace**, y conviene dejarlas dichas para que nadie las
espere:

- No guarda estado de ningún tipo. Se puede levantar en dos o diez copias sin
  coordinación.
- No valida reglas de negocio ni transforma datos de dominio. Si Gestión de
  Trabajos rechaza una categoría, el rechazo viene de allá.
- No habla con Pulsar. Ni publica ni consume.

---

## El identificador de correlación nace en el BFF

Cuando una petición entra al sistema, desencadena una reacción en cadena que
atraviesa varios servicios durante varios segundos. Si algo sale mal, hoy hay
que buscar a mano en los registros de cada servicio y adivinar qué línea
corresponde a qué petición.

El **identificador de correlación** resuelve eso: es un código único que se crea
una sola vez, al principio, y que **todos los servicios copian tal cual** en cada
mensaje que publican y en cada línea de registro que escriben. Con él, buscar una
sola cadena de texto en los registros de los seis servicios reconstruye la
historia completa de una petición, en orden.

**A partir de esta historia, ese código lo crea el BFF.** Es el lugar natural:
es la puerta por donde entra todo, y es el único punto donde una petición todavía
es una sola cosa antes de repartirse.

### Qué cambia respecto a hoy

| | Hoy | A partir de esta historia |
|---|---|---|
| Quién lo crea | Cada servicio se lo inventa por su cuenta | **El BFF**, una sola vez por petición |
| Qué valor tiene | Gestión de Trabajos y Emparejamiento usan el identificador del trabajo; Acreditación usa el del proveedor | Un código único de petición, el mismo para toda la cadena |
| Se puede seguir una petición completa | **No.** Los identificadores no coinciden entre servicios | Sí, con una sola búsqueda |
| Cubre flujos sin trabajo (acreditar un proveedor) | No | Sí |

### Cómo viaja

1. El cliente llama al BFF. Si trae su propio identificador en la cabecera
   `X-Correlation-Id`, el BFF lo respeta; si no, lo crea.
2. El BFF lo manda en esa misma cabecera a los servicios, y **lo devuelve
   siempre al cliente** en la cabecera `X-Correlation-Id` de la respuesta — en
   **todas**, incluidas las de error. Esa es justamente la respuesta en la que
   más se necesita: quien recibe un `503` o un `409` se lleva, en la misma
   respuesta, el código exacto con el que se puede buscar qué pasó.
   En las peticiones que **inician una saga** (`POST /trabajos` y
   `POST /trabajos/asignacion`) el identificador va además **en el cuerpo** de
   la respuesta, junto al identificador del trabajo: el cliente acaba de disparar
   algo que va a tardar segundos en resolverse y necesita poder guardar con qué
   seguirlo, sin depender de que su herramienta le muestre las cabeceras.
3. El servicio que recibe la petición lo pone en **cada mensaje que publica**,
   en los dos lugares donde el proyecto ya tiene un espacio previsto para él: el
   sobre del mensaje y sus propiedades.
4. El servicio que **consume** ese mensaje lo lee y lo vuelve a poner en lo que
   él publique. Así se propaga hasta el final de la cadena, sin importar cuántos
   saltos dé.
5. Cada servicio escribe el identificador en **todas** sus líneas de registro
   relacionadas con esa petición.

### Lo que no cambia: la clave de partición

> Esto se verificó en el código antes de escribirlo, porque es la pregunta que
> más importa.

El identificador de correlación y la **clave de partición** son dos cosas
completamente separadas en el proyecto, y viajan por caminos distintos:

| | Clave de partición | Identificador de correlación |
|---|---|---|
| Qué es | El identificador del trabajo | El código de la petición |
| Para qué sirve | Decidir **en qué partición** cae el mensaje, y con eso garantizar el orden dentro de un mismo trabajo | Seguir una petición por los registros |
| Dónde viaja | Argumento `partition_key` del mensaje | Campo del sobre y propiedad del mensaje |
| ¿Pulsar lo usa para enrutar? | **Sí** | **No** |

Conclusión, con nombre y apellido: en
`seedwork/infraestructura/despachadores.py` la clave y las propiedades se pasan
como dos argumentos distintos, y en `modulos/trabajos/aplicacion/handlers.py` la
clave se fija explícitamente al identificador del trabajo. **El tópico de eventos
de trabajo sigue particionándose exactamente igual.** No cambia el orden dentro
de un trabajo, ni el número de particiones, ni el tipo de suscripción.

Tampoco es un cambio de contrato: el campo del sobre **ya existe** en los cinco
contratos con su valor por defecto. Cambia lo que se escribe adentro, no la forma
del mensaje — así que no hay nada que el broker pueda rechazar.

### Dos cuidados que sí hay que tener

**1. No es un dato del negocio.** El identificador de correlación no debe
convertirse en un campo de las entidades de dominio ni en una columna de las
tablas de negocio. Es información de transporte: entra por el borde del servicio
—con la petición HTTP o con el mensaje que llega— y sale por el borde, con el
mensaje que se publica. Si termina metido en el dominio, se habrá contaminado el
modelo de negocio con una preocupación de infraestructura, que es justo lo que la
arquitectura del proyecto evita en todas partes.

**2. Quien empiece una cadena sin BFF, lo crea.** El BFF es la puerta normal,
pero no la única: las APIs de los servicios siguen abiertas, y el generador de
carga publica directo en los tópicos. La regla general es: *si llega una petición
o un mensaje sin identificador de correlación, quien lo recibe crea uno y lo
propaga desde ahí.* Así nunca hay una cadena sin identificar, venga de donde
venga.

---

## Colección de Postman

Una colección nueva, `postman/hogar-alpes-bff.postman_collection.json`, con dos
entornos (`bff-local` y `bff-aws`), organizada así:

| Carpeta | Qué prueba |
|---|---|
| `0 · Salud` | Que el BFF responde y que ve a los seis componentes |
| `1 · Trabajos` | Crear, consultar y cambiar de estado, a través del BFF |
| `2 · Acreditaciones` | Solicitar, aprobar, revocar, consultar y ver el historial |
| `3 · Emparejamiento` | Buscar candidatos y consultar un emparejamiento |
| `4 · Seguimiento` | Consultar el seguimiento y los conteos de Operaciones |
| `5 · Sagas` | Consultar el estado de una transacción y el resumen general |
| `6 · Endpoints compuestos` | Las cuatro rutas que solo existen en el BFF |
| `7 · Saga de punta a punta` | Los cuatro casos de US-01 (exitoso y tres fallos), disparados y verificados desde el BFF |
| `8 · Errores y degradación` | Ruta inexistente, identificador inexistente, y el comportamiento cuando un servicio de atrás está caído |
| `9 · Trazabilidad` | Que el BFF crea el identificador de correlación cuando no viene, que respeta el que el cliente manda, y que **lo devuelve en la cabecera de toda respuesta** — incluidas las de error y las de servicio caído |

Todas las peticiones traen aserciones automáticas, igual que la colección
actual, y la colección completa tiene que correr en verde con `newman`.

---

## Criterios de aceptación

### Sobre el servicio

- [ ] **CA-2.1** — El BFF corre como un contenedor más en `docker compose up` y
      responde en su puerto sin configuración manual adicional.
- [ ] **CA-2.2** — Está escrito en **Python con Flask y gunicorn**, las mismas
      versiones que usan los demás servicios. **No se agrega ningún framework
      nuevo**; las llamadas HTTP hacia adentro se hacen con la biblioteca
      estándar de Python, igual que ya lo hace `herramientas/medir_latencia.py`.
- [ ] **CA-2.3** — El BFF **no tiene base de datos ni conexión al broker**. Se
      verifica revisando que no declara ningún volumen de datos, ninguna
      variable de conexión a PostgreSQL y ninguna dependencia de Pulsar.
- [ ] **CA-2.4** — Las direcciones de los servicios de atrás se configuran por
      variables de entorno, con valores por defecto que funcionan en Compose.
      Cambiar de local a AWS o a Kubernetes no exige tocar código.

### Sobre el reenvío

- [ ] **CA-2.5** — Cada una de las rutas de los cinco servicios está disponible
      a través del BFF, con la misma ruta, el mismo cuerpo y el mismo código de
      respuesta que si se llamara directo al servicio.
- [ ] **CA-2.6** — **La colección de Postman de la Entrega 4 pasa en verde
      contra el BFF con solo cambiar la dirección base del entorno.** Esta es la
      prueba más fuerte de que el reenvío es fiel: la misma colección, las
      mismas aserciones, otra puerta de entrada.
- [ ] **CA-2.7** — Los errores de negocio de los servicios llegan al cliente sin
      cambiar: un `400` por una categoría no permitida en México sigue siendo un
      `400` con su mismo mensaje.

### Sobre los endpoints compuestos

- [ ] **CA-2.8** — `GET /trabajos/{id}/completo` devuelve, en una sola
      respuesta, el trabajo, su seguimiento, su emparejamiento y el estado de su
      saga.
- [ ] **CA-2.9** — Si uno de los servicios de atrás está caído, el endpoint
      compuesto **devuelve lo que sí pudo obtener** y marca lo que falta como no
      disponible, en lugar de fallar completo.
- [ ] **CA-2.10** — `GET /estado-del-sistema` reporta la salud de los seis
      componentes y el resumen de sagas por estado, en una sola llamada.
- [ ] **CA-2.11** — Los endpoints compuestos resuelven en menos de **dos
      segundos** en condiciones normales.

### Sobre el aislamiento entre servicios

- [ ] **CA-2.12** — **Agregar el BFF no crea una ruta de red entre dos servicios
      de dominio.** El BFF alcanza a los seis; los seis siguen sin alcanzarse
      entre sí. Se verifica con la misma comprobación que ya existe para las
      bases de datos: desde el contenedor de un servicio, el nombre de otro
      servicio no debe resolver.
- [ ] **CA-2.13** — Ningún servicio de dominio adquiere un cliente HTTP ni una
      variable de entorno que apunte a otro servicio de dominio o al BFF. El
      tráfico solo va del BFF hacia adentro, nunca al revés.

### Sobre el manejo de fallos

- [ ] **CA-2.14** — Con un servicio de atrás detenido, sus rutas devuelven `503`
      con un mensaje que nombra el servicio, y **las rutas de los demás
      servicios siguen funcionando con normalidad**.
- [ ] **CA-2.15** — El BFF nunca devuelve una traza de error ni un `500` sin
      explicación.
### Sobre el identificador de correlación

- [ ] **CA-2.16** — El BFF **crea** un identificador de correlación único cuando
      la petición no trae uno, y **respeta** el que venga en la cabecera
      `X-Correlation-Id` si el cliente lo manda.
- [ ] **CA-2.17** — El BFF **devuelve el identificador en la cabecera
      `X-Correlation-Id` de todas sus respuestas**, sin excepción: las
      correctas, las de error de negocio (`400`, `404`, `409`) y las de servicio
      no disponible (`503`). Se verifica revisando las cabeceras de una respuesta
      de cada tipo, no solo de una exitosa.
- [ ] **CA-2.17b** — Las peticiones que **inician una saga** devuelven además el
      identificador **en el cuerpo** de la respuesta, junto al identificador del
      trabajo, para que el cliente pueda guardarlo y seguir la transacción
      después.
- [ ] **CA-2.17c** — El identificador que devuelve el BFF es **el mismo** que
      llega a los mensajes publicados y a las líneas de registro de los
      servicios. Se verifica tomando el valor de una respuesta y buscándolo: es
      la puerta de entrada al criterio CA-2.18.
- [ ] **CA-2.18** — **Una sola búsqueda del identificador en los registros de los
      seis servicios reconstruye la cadena completa de una petición, en orden.**
      Se verifica sobre un caso real de saga: una búsqueda, todos los pasos.
- [ ] **CA-2.19** — Cada servicio pone el identificador que recibió en **cada
      mensaje que publica**, tanto en el sobre como en las propiedades, y lo lee
      del mensaje que consume para volver a propagarlo. Se verifica inspeccionando
      un mensaje real en el broker.
- [ ] **CA-2.20** — **La clave de partición del tópico de eventos de trabajo
      sigue siendo el identificador del trabajo.** Se verifica revisando que
      todos los mensajes de un mismo trabajo caen en la misma partición, y que
      el escenario de escalabilidad sigue comprobando el orden dentro de un
      trabajo sin cambios.
- [ ] **CA-2.21** — El identificador de correlación **no aparece** en ninguna
      entidad de dominio ni en ninguna tabla de negocio de los servicios.
- [ ] **CA-2.22** — Una petición que **no** pasa por el BFF —directa a la API de
      un servicio, o publicada por el generador de carga en un tópico— también
      queda identificada: quien la recibe crea el identificador si no viene.

### Sobre la colección de Postman

- [ ] **CA-2.23** — Existe `postman/hogar-alpes-bff.postman_collection.json` con
      las diez carpetas descritas y al menos una aserción por petición.
- [ ] **CA-2.24** — Existen los entornos `bff-local` y `bff-aws`.
- [ ] **CA-2.25** — La colección completa corre en verde con `newman`, sin
      intervención manual, contra un sistema recién levantado.
- [ ] **CA-2.26** — La carpeta *«Saga de punta a punta»* demuestra desde el BFF
      el caso exitoso y los tres casos de fallo de US-01, verificando el estado
      final de la saga en cada uno.

### Documentación

- [ ] **CA-2.27** — El `README.md` del proyecto explica qué es el BFF, por qué
      existe, y que **sigue siendo válido** llamar directo a cada servicio
      (el BFF es una puerta adicional, no obligatoria).
- [ ] **CA-2.28** — `servicios/bff/README.md` lista todas las rutas, a qué
      servicio va cada una, qué devuelve cada endpoint compuesto, y **cómo
      seguir una petición por los registros** usando el identificador de
      correlación.

---

## Lo que **no** entra en esta historia

- **No hay autenticación ni autorización.** El BFF no valida credenciales, no
  emite ni verifica tokens. El *Gateway de Partners* del enunciado original —que
  sí implicaría aislamiento por cliente— no es parte de esta historia.
- **No hay límites de tasa ni control de consumo por cliente.**
- **No hay caché.** Cada petición al BFF produce las peticiones correspondientes
  hacia adentro.
- **No hay una interfaz gráfica.** El BFF es una API; la colección de Postman es
  la forma de usarla.
- **No hay GraphQL ni ningún esquema nuevo de consulta.** Sería un framework
  nuevo, y está explícitamente excluido.
- **No se retiran ni se cierran las APIs de los servicios.** Siguen expuestas y
  siguen siendo la forma en que los escenarios de calidad se miden.

---

## Riesgos y cosas que hay que tener en cuenta

| # | Riesgo | Cómo se maneja |
|---|---|---|
| R5-6 | **El BFF se vuelve un punto único de falla.** Si se cae, se cae la puerta de entrada | Es un servicio sin estado: se pueden levantar varias copias. Y las APIs de los servicios siguen abiertas, así que existe un camino alterno |
| R5-7 | **Agregar el BFF podría abrir, sin querer, una ruta de red entre dos servicios de dominio** — que es justo lo que el proyecto promete que no existe | Se resuelve con una red por cada par BFF–servicio, en lugar de una red compartida por todos. Es el criterio CA-2.12, y hay que verificarlo, no suponerlo |
| R5-8 | **Los endpoints compuestos pueden parecer lentos** porque suman la latencia de varias llamadas | Las llamadas de un endpoint compuesto se hacen en paralelo, no una tras otra, y cada una tiene su propio tiempo límite |
| R5-9 | **La consistencia eventual se nota más desde el BFF**: un trabajo recién creado todavía no tiene seguimiento ni emparejamiento | El endpoint compuesto lo reporta como *«todavía no disponible»*, que es la verdad, en lugar de un `404` que parecería un error |
| R5-10 | **Duplicar en el BFF la lista de rutas de cinco servicios se puede desactualizar** | La colección de Postman del BFF y la de los servicios prueban las mismas operaciones: si una ruta cambia y el BFF no, la colección lo detecta |
| R5-10b | **La cadena de correlación se rompe en un solo eslabón olvidado.** Basta con que un servicio no copie el identificador al publicar para que la traza se pierda a partir de ahí, y nada falla ni avisa | La verificación no es «está el código»: es la búsqueda única del criterio CA-2.18 sobre una saga real. Si un eslabón falta, la cadena sale incompleta y se ve de inmediato |
| R5-10c | **El identificador podría terminar metido en el dominio** por el camino corto: agregarlo como campo a los comandos y a los eventos de negocio | Se resuelve haciéndolo viajar por el borde de cada servicio —de la petición o el mensaje entrante al mensaje saliente—, nunca a través del modelo de negocio. Es el criterio CA-2.21 |

---

## Definición de terminado

- [ ] Los treinta criterios de aceptación se cumplen y están verificados.
- [ ] El BFF corre en `docker compose up` junto con todo lo demás.
- [ ] Las dos colecciones de Postman —la de los servicios y la del BFF— corren
      en verde con `newman`.
- [ ] `servicios/bff/tests/` tiene pruebas automáticas del reenvío, de la
      composición y del comportamiento ante un servicio caído, sin necesitar
      los servicios reales.
- [ ] La decisión de diseño queda anotada en `docs/decisiones.md`.
- [ ] `docs/actividades.md` registra quién lo hizo, con enlaces a sus *commits*
      y a su *pull request*.
