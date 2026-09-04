# Guía de estudio: patrones de diseño en Gestión de Trabajos

Este documento explica, en lenguaje simple, **qué patrones usa el código, cómo
funcionan y por qué se eligieron**. Está pensado para sustentar la entrega ante
un evaluador y para que cualquier persona del equipo —junior o senior— pueda
entender el "por qué" detrás de cada carpeta del proyecto.

No es un documento teórico: cada sección apunta a un archivo real del
repositorio. Si algo suena abstracto, el código está a un clic de distancia.

---

## 1. La idea central en una frase

> El **dominio** (las reglas del negocio) vive aislado en el centro del
> proyecto y no sabe nada de bases de datos, HTTP o colas de mensajes. Todo lo
> demás —Postgres, Pulsar, Flask— son detalles que **se conectan al dominio**,
> nunca al revés.

Esa sola regla explica casi todas las decisiones que vienen a continuación:
por qué hay "puertos", por qué los eventos se dividen en dos tipos, por qué
existen fábricas y mapeadores en vez de simplemente guardar objetos en la
base de datos.

---

## 2. Mapa mental: problema de negocio → patrón → dónde vive

| Problema que hay que resolver | Patrón que lo resuelve | Carpeta / archivo |
|---|---|---|
| "Un Trabajo tiene reglas: no puede pasar de CREADO a COMPLETADO directamente" | Objeto Valor + Reglas de negocio | `dominio/objetos_valor.py`, `dominio/reglas.py` |
| "Un Trabajo y sus SubTrabajos deben cambiar juntos, de forma consistente" | Agregado / Raíz de Agregado | `dominio/entidades.py` |
| "Construir un Trabajo válido es más que un `Trabajo(...)`" | Fábrica | `dominio/fabricas.py` |
| "El dominio necesita guardar y leer datos sin saber qué base de datos hay detrás" | Repositorio (puerto) + adaptador | `dominio/repositorios.py` + `infraestructura/repositorios.py` |
| "Cuando algo importante ocurre, otras partes del sistema deben enterarse" | Eventos de dominio / integración | `dominio/eventos.py`, `seedwork/infraestructura/uow.py` |
| "Escribir (`crear un trabajo`) y leer (`consultar un trabajo`) son operaciones distintas" | CQS (Command-Query Separation) | `seedwork/aplicacion/comandos.py`, `queries.py` |
| "Si la base de datos falla a mitad de camino, no debe quedar todo a medias" | Unidad de Trabajo (Unit of Work) | `seedwork/infraestructura/uow.py` |
| "El módulo `operaciones` necesita reaccionar a lo que pasa en `trabajos` sin acoplarse a él" | Arquitectura orientada a eventos | `modulos/operaciones/aplicacion/handlers.py` |
| "Cambiar de Postgres a otro motor no debería tocar el dominio" | Arquitectura hexagonal (puertos y adaptadores) | todo `infraestructura/` vs `dominio/` |

---

## 3. Domain-Driven Design (DDD): los bloques de construcción

DDD no es una tecnología, es una forma de **organizar el código alrededor del
lenguaje y las reglas del negocio**, en vez de organizarlo alrededor de tablas
de base de datos o de un framework. Para lograrlo usa un vocabulario de piezas
reutilizables. Aquí están, una por una.

### 3.1 Entidad

**En palabras simples:** un objeto que importa **quién es**, no solo qué
valores tiene. Dos entidades con los mismos datos pero distinto `id` son
cosas distintas. Si sus datos cambian con el tiempo, sigue siendo "la misma"
entidad.

**Analogía:** una persona. Si cambias de apellido no te conviertes en otra
persona — tu cédula (tu identidad) no cambió.

**Dónde está:** `seedwork/dominio/entidades.py`

```python
@dataclass
class Entidad:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    fecha_creacion: datetime = field(default_factory=datetime.utcnow)
    fecha_actualizacion: datetime = field(default_factory=datetime.utcnow)

    def __eq__(self, other) -> bool:
        return self.id == other.id   # se compara por identidad, no por valores
```

`Trabajo` y `SubTrabajo` (en `modulos/trabajos/dominio/entidades.py`) heredan
de esto: cada uno tiene un `id` propio y persiste a través de sus cambios de
estado.

### 3.2 Objeto Valor (Value Object)

**En palabras simples:** lo opuesto a una Entidad. Es un objeto que importa
**por lo que vale**, no por quién es. No tiene identidad ni ciclo de vida
propio. Si dos objetos valor tienen los mismos datos, son intercambiables. Y
son **inmutables**: en vez de modificarlos, se crea uno nuevo.

**Analogía:** un billete de $10.000. No te importa *cuál* billete específico
tienes en la cartera, solo que vale $10.000. Si te lo cambian por otro
billete de $10.000, no perdiste nada.

**Dónde está:** `seedwork/dominio/objetos_valor.py` (la base) y
`modulos/trabajos/dominio/objetos_valor.py` (los concretos):

```python
@dataclass(frozen=True)          # frozen = inmutable, no se puede mutar
class EstadoTrabajo(ObjetoValor):
    valor: Estado = Estado.CREADO

    def puede_transicionar_a(self, destino: Estado) -> bool:
        return destino in TRANSICIONES.get(self.valor, set())
```

Fíjate que `EstadoTrabajo` no solo guarda un dato: **sabe responder
preguntas sobre sí mismo** (`puede_transicionar_a`). Esto es intencional en
DDD: un Objeto Valor no es un DTO tonto, encapsula comportamiento relacionado
con ese dato. Por eso, agregar el estado `EN_VERIFICACION` al ciclo de vida
del negocio se resuelve tocando **un solo archivo** — el diccionario
`TRANSICIONES` — sin tocar la agregación `Trabajo`.

Otros ejemplos: `Categoria`, `Ubicacion`, `Solicitante`, `Urgencia`. Ninguno
tiene `id`; se comparan por sus atributos.

### 3.3 Agregado y Raíz de Agregado

**En palabras simples:** un grupo de entidades y objetos valor que deben
mantenerse **consistentes entre sí como una sola unidad**. Desde afuera, solo
se puede entrar al grupo a través de una puerta única: la **raíz del
agregado**. Nadie modifica una pieza interna directamente.

**Analogía:** un pedido de restaurante con varios platos. No modificas un
plato individual sin pasar por "el pedido" — si cancelas el pedido, se
cancelan todos sus platos; el mesero nunca le habla directamente a un plato,
le habla al pedido.

**Dónde está:** `modulos/trabajos/dominio/entidades.py`

```python
@dataclass
class Trabajo(AgregacionRaiz, ValidarReglasMixin):
    sub_trabajos: list[SubTrabajo] = field(default_factory=list)

    def cambiar_estado(self, destino: Estado):
        self.validar_regla(TransicionDeEstadoValida(self.estado, destino))
        ...
```

`Trabajo` es la **raíz**; `SubTrabajo` vive **dentro** de su límite. Esto fue
una decisión de diseño explícita (documentada en el docstring del archivo):
`SubTrabajo` podría haber sido su propia raíz independiente, ganando
concurrencia, pero se prefirió meterlo dentro de `Trabajo` para no perder
consistencia inmediata (si actualizas un sub-trabajo, no puede quedar
desincronizado del trabajo padre). Ninguna decisión de diseño es gratis: acá
se documentó el trade-off en vez de ignorarlo.

### 3.4 Fábrica (Factory)

**En palabras simples:** cuando construir un objeto es más complicado que
`MiClase(a, b, c)` — porque hay que validar cosas, transformar datos externos,
o decidir qué tipo concreto crear — esa complejidad se saca del constructor y
se mete en una clase aparte cuyo único trabajo es "saber construir".

**Analogía:** no armas un mueble de IKEA con la mano invisible del destino;
sigues instrucciones que garantizan que el mueble quede bien armado antes de
usarlo. La fábrica es esas instrucciones.

**Dónde está:** `modulos/trabajos/dominio/fabricas.py`

```python
class FabricaTrabajos(Fabrica):
    def crear_objeto(self, obj, mapeador: Mapeador = None) -> any:
        if mapeador.obtener_tipo() == Trabajo:
            return _FabricaTrabajo().crear_objeto(obj, mapeador)
        raise TipoObjetoNoExisteEnDominioTrabajosExcepcion()
```

Aquí la fábrica se apoya en un **Mapeador** para traducir un DTO (los datos
que llegaron del HTTP) hacia la entidad de dominio `Trabajo`. La garantía que
da la fábrica: **un `Trabajo` nunca existe a medio construir o en un estado
inválido**.

### 3.5 Repositorio (el "puerto" hacia los datos)

**En palabras simples:** una interfaz que dice "así se guardan y se leen
agregados", sin decir *cómo*. El dominio conoce la interfaz (el puerto); la
infraestructura decide si eso se traduce a SQL de Postgres, a un archivo, o a
lo que sea.

**Analogía:** un enchufe de pared. Tu lámpara (el dominio) solo necesita
saber que existe un enchufe de 110V. No le importa si la electricidad viene
de una hidroeléctrica o de un panel solar (la infraestructura). Cambiar la
fuente de energía no obliga a rediseñar la lámpara.

**Dónde está el puerto (abstracto):** `seedwork/dominio/repositorios.py`

```python
class Repositorio(ABC):
    @abstractmethod
    def obtener_por_id(self, id: UUID) -> Entidad: ...
    @abstractmethod
    def agregar(self, entidad: Entidad): ...
```

**Dónde está el adaptador (concreto):**
`modulos/trabajos/infraestructura/repositorios.py`

```python
class RepositorioTrabajosPostgres(RepositorioTrabajos):
    def agregar(self, trabajo: Trabajo):
        db.session.add(self.mapeador.entidad_a_dto(trabajo))
```

Si mañana el proyecto migra a MongoDB, se escribe
`RepositorioTrabajosMongo` implementando el mismo puerto, y **ni un solo
archivo de `dominio/` o `aplicacion/` cambia**. Eso es exactamente el
escenario de calidad de modificabilidad #1 que el README declara.

### 3.6 Servicio de Dominio

**En palabras simples:** hay lógica de negocio que no pertenece naturalmente
a ninguna Entidad ni Objeto Valor específico — por ejemplo, algo que depende
de una fuente de información externa. Esa lógica se pone en un Servicio de
Dominio, para no forzarla dentro de una entidad donde no encaja.

**Dónde está:** `modulos/trabajos/dominio/servicios.py`

```python
class ServicioReglasRegionales(ServicioDominio, ABC):
    @abstractmethod
    def categorias_permitidas(self, pais: str) -> list[str]: ...
```

El dominio declara *qué necesita saber* (qué categorías aplican en un país),
pero no sabe *de dónde sale* esa respuesta. El adaptador
(`infraestructura/reglas_regionales.py`) hoy lee un JSON local; podría ser una
llamada HTTP a un sidecar real sin que el dominio se entere.

### 3.7 Reglas de negocio (patrón Especificación)

**En palabras simples:** en vez de meter `if`s de validación dispersos por
todo el código, cada regla de negocio se convierte en un objeto con un solo
método: `es_valido()`. Esto las hace nombrables, testeables una por una, y
reutilizables.

**Dónde está:** `seedwork/dominio/reglas.py` + `modulos/trabajos/dominio/reglas.py`

```python
class TransicionDeEstadoValida(ReglaNegocio):
    def es_valido(self) -> bool:
        return self.actual.puede_transicionar_a(self.destino)
```

Y se invoca así, desde la agregación:

```python
def cambiar_estado(self, destino: Estado):
    self.validar_regla(TransicionDeEstadoValida(self.estado, destino))
```

Si la regla falla, se lanza `ReglaNegocioExcepcion` — una excepción **del
dominio**, que no sabe nada de HTTP. Es la capa de arriba (`api/trabajos.py`)
la que decide traducir esa excepción a un `409` o un `400`.

### 3.8 Eventos de dominio

**En palabras simples:** un evento de dominio es un **hecho que ya pasó**,
contado en pasado ("TrabajoCreado", no "CrearTrabajo"). Se usa para que unas
partes del sistema le cuenten a otras "esto ocurrió", sin que la parte que
cuenta necesite saber quién está escuchando.

**Dónde está:** `seedwork/dominio/eventos.py` (base) y
`modulos/trabajos/dominio/eventos.py` (concretos: `TrabajoCreado`,
`EstadoTrabajoCambiado`, `SubTrabajoAgregado`).

```python
def crear(self, categorias_permitidas, urgencias_permitidas):
    ...
    self.agregar_evento(TrabajoCreado(trabajo_id=self.id, ...))
```

Importante: la agregación **no publica el evento**, solo lo **acumula** en
una lista (`self.eventos`). Publicarlo es responsabilidad de otra pieza (la
Unidad de Trabajo, sección 6). Esta separación es deliberada: el dominio no
debe saber si hay pydispatch, Kafka, Pulsar o nada detrás.

Esto se explica en profundidad en la sección 7 (arquitectura orientada a
eventos), porque es uno de los puntos centrales de la rúbrica.

### 3.9 Módulos (Bounded Contexts)

**En palabras simples:** un sistema grande no puede modelarse con un único
diccionario de significados compartido por todos. DDD propone dividir el
sistema en **módulos con límites explícitos**, donde cada palabra tiene un
significado propio y consistente *dentro* de ese límite.

**Dónde está:** `modulos/trabajos/` y `modulos/operaciones/`.

`trabajos` modela el ciclo de vida operativo de un trabajo (crear, cambiar de
estado). `operaciones` modela el seguimiento de SLA de ese mismo trabajo,
pero con su **propio** vocabulario (`SeguimientoOperativo`, `VentanaSLA`,
`Prioridad`) y su **propia** agregación. `operaciones` no importa ni una
línea de `trabajos` — se entera de que un trabajo existe únicamente porque
recibe un evento de dominio y lo lee por sus atributos. Esto es justo lo que
un Bounded Context busca evitar: que dos módulos terminen acoplados a nivel
de compilación.

### 3.10 Seedwork

**En palabras simples:** un "kit de piezas base" (Entidad, ObjetoValor,
Repositorio, Comando, Query, UnidadDeTrabajo...) que todos los módulos
reutilizan para no reinventar la rueda en cada uno.

**La decisión que vale la pena entender:** el `seedwork` de este servicio
**no es una librería compartida** entre los nueve microservicios de la
arquitectura completa. Es una **copia**, versionada junto con este servicio.
Si un microservicio necesita una versión distinta de `Repositorio` mañana, la
cambia sin coordinar un release de una librería compartida con los otros
ocho servicios. El costo aceptado es algo de duplicación de código entre
servicios; el beneficio es que ningún servicio puede romper a otro por un
cambio en una dependencia común — que es precisamente lo que una arquitectura
de microservicios busca evitar.

---

## 4. Arquitectura Hexagonal (puertos y adaptadores)

**La idea en una frase:** el dominio se dibuja en el centro de un hexágono;
todo lo que lo rodea (HTTP, base de datos, colas de mensajes) son
**adaptadores** que se conectan al dominio a través de **puertos**
(interfaces). La flecha de dependencia siempre apunta **hacia adentro**.

```
        ADAPTADORES DE ENTRADA                    ADAPTADORES DE SALIDA
   ┌──────────────────────────┐            ┌──────────────────────────────┐
   │ api/trabajos.py   (HTTP) │            │ repositorios.py   PostgreSQL │
   │ consumidores.py   Pulsar │            │ despachadores.py  Pulsar     │
   └────────────┬─────────────┘            │ reglas_regionales.py sidecar │
                │                          └───────────────▲──────────────┘
                ▼                                          │  implementan
        ┌───────────────────────────────────────────┐      │
        │ APLICACIÓN — comandos · queries · DTOs    │      │
        ├───────────────────────────────────────────┤      │
        │ DOMINIO — agregaciones, objetos valor,    │──────┘
        │ eventos, reglas, fábricas, PUERTOS        │  (inversión de dependencias)
        └───────────────────────────────────────────┘
```

**¿Por qué "puerto" y no simplemente "interfaz"?** Es la misma idea, con un
matiz: un puerto se piensa desde el punto de vista del dominio ("esto es lo
que yo, el dominio, necesito del mundo exterior"), no desde el punto de vista
de la tecnología ("esto es lo que Postgres ofrece"). Por eso el puerto
`Repositorio` (sección 3.5) no tiene ni un solo detalle de SQL: solo tiene los
verbos que el dominio necesita (`agregar`, `obtener_por_id`...).

**Adaptadores de entrada (primarios)** — algo de afuera *le pide algo* al
sistema:
- `api/trabajos.py`: HTTP síncrono. Traduce una petición REST en un
  `Comando` o una `Query` y despacha.
- `infraestructura/consumidores.py`: consumidor de Pulsar. Traduce un mensaje
  de la cola `cmd-trabajo` en el mismo `Comando` `CrearTrabajo`.

Nótese algo importante: **ambos adaptadores de entrada terminan llamando
exactamente al mismo `ejecutar_comando(comando)`**. Eso es prueba de que la
capa de aplicación no sabe (ni le importa) si la petición vino de un humano
tocando un botón o de un mensaje en una cola.

**Adaptadores de salida (secundarios)** — el sistema *le pide algo* al mundo
exterior:
- `infraestructura/repositorios.py`: implementa el puerto `Repositorio` sobre
  SQLAlchemy/PostgreSQL.
- `infraestructura/despachadores.py`: implementa la publicación de eventos
  sobre Apache Pulsar.
- `infraestructura/reglas_regionales.py`: implementa el puerto
  `ServicioReglasRegionales` leyendo un JSON.

**¿Por qué importa esto para la rúbrica?** Porque demuestra que el diseño no
es "until it works", sino que anticipa cambio: reemplazar Postgres, cambiar
el broker, o mover el sidecar regional a un servicio real desplegado aparte
son cambios que **solo tocan un adaptador**, nunca el dominio.

---

## 5. CQS (Command-Query Separation)

**La idea en una frase:** una operación **o** cambia el estado del sistema
(comando) **o** devuelve datos (consulta), nunca ambas cosas a la vez. Mezclar
las dos responsabilidades en un mismo método es lo que CQS prohíbe.

> Nota de vocabulario: esto es **CQS** (a nivel de método/operación), el
> hermano más simple de **CQRS** (Command Query Responsibility *Segregation*),
> que además separa los *modelos de datos* de lectura y escritura (por
> ejemplo, con bases de datos distintas). Este proyecto aplica CQS: separa
> las *operaciones*, no necesariamente el almacenamiento físico.

**Dónde está:** `seedwork/aplicacion/comandos.py` y `queries.py`

```python
@dataclass
class Comando(ABC): ...          # una intención de cambio. No devuelve datos.

@singledispatch
def ejecutar_comando(comando):
    raise NotImplementedError(...)
```

```python
@dataclass
class Query(ABC): ...            # una petición de datos. No muta nada.

@singledispatch
def ejecutar_query(query) -> QueryResultado:
    raise NotImplementedError(...)
```

`singledispatch` es una utilidad de Python: permite tener **una función
"genérica"** (`ejecutar_comando`) que internamente elige qué código correr
según **el tipo del argumento** que recibe. Así, `api/trabajos.py` nunca
necesita un `if isinstance(...)`; cada módulo registra su propio handler:

```python
@ejecutar_comando.register(CrearTrabajo)
def ejecutar_comando_crear_trabajo(comando: CrearTrabajo):
    return CrearTrabajoHandler().handle(comando)
```

**Cómo se ve desde afuera (la API HTTP):**

| | Escritura (Comando) | Lectura (Query) |
|---|---|---|
| Ejemplo | `CrearTrabajo`, `CambiarEstadoTrabajo` | `ObtenerTrabajo`, `ObtenerTrabajosPorEstado` |
| Ruta HTTP | `POST /trabajos` | `GET /trabajos/<id>` |
| Código de respuesta | `202 Accepted` (se aceptó, se procesa) | `200 OK` (aquí están los datos) |
| ¿Qué devuelve? | Solo el `id` | Los datos completos |

**¿Por qué el `202` y no `200` o `201`?** Porque el comando no garantiza que
el trabajo ya quedó totalmente procesado en el instante en que responde —
solo garantiza que la intención fue aceptada. Esto es honesto con el cliente
de la API y es lo que permite absorber picos de tráfico (ver sección 7):
el servidor no promete "ya lo hice", promete "ya lo recibí".

---

## 6. Unidad de Trabajo (Unit of Work)

**La idea en una frase:** cuando una operación de negocio toca varias tablas
o varios agregados, todos esos cambios deben confirmarse **juntos o
ninguno**. La Unidad de Trabajo (UoW) es el objeto que lleva la cuenta de "lo
que hay que hacer" y lo ejecuta como una sola transacción.

**Dónde está:** `seedwork/infraestructura/uow.py`

```python
def commit(self):
    for batch in self.batches:
        batch.operacion(*batch.args, **batch.kwargs)
    self._commit()                      # commit real de la base de datos
    self.publicar_eventos_integracion()
    self._limpiar_batches()
```

`registrar_batch` no ejecuta nada de inmediato — solo **anota** la operación
(`repositorio.agregar`, `repositorio.actualizar`, con sus argumentos) para
correrla más tarde, todas juntas, dentro de la misma transacción SQL.

**El detalle que conecta la UoW con los eventos** (ver sección 7): la UoW es
también quien decide **cuándo** se publica cada tipo de evento — antes o
después del commit. Esa decisión no es un detalle menor, es el corazón de
cómo este proyecto hace arquitectura orientada a eventos de forma segura.

---

## 7. Arquitectura orientada a eventos: el punto más importante de la rúbrica

Este proyecto usa **dos tipos de eventos**, con dos mecanismos de entrega
distintos, publicados en **dos momentos** distintos. Entender por qué existen
ambos — y no solo uno — es la parte que más vale la pena poder explicar.

### 7.1 Eventos de dominio (síncronos, en proceso)

- **Qué son:** el mecanismo por el cual **los módulos de este mismo servicio
  se hablan entre sí** (`trabajos` → `operaciones`).
- **Cuándo se publican:** *antes* del commit a la base de datos.
- **Cómo viajan:** con la librería `pydispatch`, en memoria, en el mismo
  hilo. No hay red ni cola de por medio.

```python
def publicar_eventos_dominio(self):
    for evento in self._eventos_pendientes('dominio'):
        dispatcher.send(signal=f'{type(evento).__name__}Dominio', evento=evento)
```

Cuando esto se ejecuta, `HandlerSeguimientoDominio.handle_trabajo_creado` (en
`modulos/operaciones/aplicacion/handlers.py`) corre **inmediatamente**, en la
misma llamada. Y lo interesante: ese handler **se une a la misma Unidad de
Trabajo** (`UnidadTrabajoPuerto.registrar_batch(...)`), así que si el commit
falla después, el seguimiento operativo que `operaciones` estaba creando
**tampoco queda guardado**. No puede haber un `SeguimientoOperativo` huérfano
de un `Trabajo` que nunca llegó a existir.

**Analogía:** es como dos personas conversando en la misma sala. No hay
delay, no hay riesgo de que el mensaje se pierda en el camino — pero también
significa que si una persona se desmaya a mitad de la frase (falla la
transacción), lo que dijo antes tampoco cuenta.

### 7.2 Eventos de integración (asíncronos, vía broker)

- **Qué son:** el mecanismo por el cual **este servicio le anuncia al resto
  del sistema** (otros microservicios) que algo ocurrió.
- **Cuándo se publican:** *después* de que el commit ya fue exitoso.
- **Cómo viajan:** serializados en Avro (`infraestructura/schema/v1/`) y
  publicados en un tópico de Apache Pulsar (`evt-trabajo`).

```python
def publicar_eventos_integracion(self):
    for evento in self._eventos_pendientes('integracion'):
        dispatcher.send(signal=f'{type(evento).__name__}Integracion', evento=evento)
```

Un handler dedicado (`HandlerTrabajoIntegracion`, en
`modulos/trabajos/aplicacion/handlers.py`) escucha esa señal y llama al
`Despachador`, que sí abre una conexión de red hacia Pulsar. Quien consuma
ese tópico —potencialmente otro de los nueve microservicios de la
arquitectura— se entera del hecho **de forma desacoplada en el tiempo**: no
tiene por qué estar escuchando en el mismo instante en que ocurrió.

**Analogía:** es como enviar una carta certificada. No es instantáneo, pero
queda un registro, y el que la recibe puede estar del otro lado del mundo, en
otro momento, sin que tú tengas que esperar a que la lea.

### 7.3 ¿Por qué el orden (dominio antes, integración después) no es un detalle?

Esta es la pregunta que más vale la pena poder responder en la
sustentación:

> Si el evento de integración saliera **antes** del commit y la transacción
> fallara después (por ejemplo, un error de base de datos), el servicio
> habría anunciado al resto del mundo un hecho que **nunca ocurrió**. Otro
> microservicio pudo haber reaccionado a "un trabajo fue creado" cuando en
> realidad no existe ningún trabajo. Ese tipo de inconsistencia es muy difícil
> de deshacer una vez que salió por la red.
>
> Publicar primero hacia adentro (dominio) y después hacia afuera
> (integración, solo si el commit tuvo éxito) es lo que garantiza que un
> evento de integración **siempre afirma un hecho verdadero**.

Este es un ejemplo real, aplicado, del principio "no anunciar lo que no pasó"
que en la literatura se conoce como parte del patrón **Transactional
Outbox** simplificado: aquí no hay una tabla outbox separada, pero el
**orden estricto** (`_commit()` antes de `publicar_eventos_integracion()`) es
la misma idea de fondo, resuelta con lo mínimo necesario para esta entrega.

### 7.4 Comandos: también hay una vía síncrona y una asíncrona

Además de los eventos, este servicio también recibe **comandos** por dos
vías:

- **Síncrona:** `POST /trabajos` ejecuta `ejecutar_comando(...)` dentro del
  mismo request HTTP.
- **Asíncrona:** un hilo aparte (`threading.Thread`, ver
  `src/gestion_trabajos/__init__.py`) corre
  `infraestructura/consumidores.py`, que escucha el tópico `cmd-trabajo` de
  Pulsar y ejecuta exactamente el mismo `ejecutar_comando(...)` cuando llega
  un mensaje.

Esto es lo que sostiene el escenario de calidad de escalabilidad: si llega un
pico de tráfico ×4, el servicio no tiene que rechazar solicitudes ni que el
que llama espere — el comando se encola en Pulsar y este servicio lo va
"drenando" a su propio ritmo.

### 7.5 ¿Los eventos son "gordos" o "flacos"?

Esta es otra decisión de diseño que vale la pena poder sustentar: **qué tanta
información se mete dentro de un evento**. En la literatura de arquitectura
orientada a eventos se habla de dos extremos:

- **Evento flaco / ligero** (también llamado *event notification*): lleva lo
  mínimo indispensable — típicamente un identificador y el tipo de evento
  ("el Trabajo X cambió"). Si el que escucha necesita más contexto, tiene que
  **llamar de vuelta** (callback) al servicio productor: una consulta HTTP,
  una query a su base de datos, etc.
- **Evento gordo** (también llamado *event-carried state transfer*): lleva
  copiada, dentro del mismo mensaje, toda la información que un consumidor
  razonable necesitaría para actuar — de modo que **nunca tiene que
  preguntarle nada de vuelta al productor**.

Ninguno de los dos es "el correcto" en abstracto; es un trade-off:

| | Evento flaco | Evento gordo |
|---|---|---|
| Tamaño del mensaje | pequeño | más grande |
| ¿El consumidor depende de que el productor esté disponible en ese momento? | **Sí** — necesita hacerle un callback | **No** — ya tiene todo lo que necesita |
| ¿Cuánto del modelo interno del productor queda expuesto? | poco | más — hay más campos que versionar con cuidado |
| ¿Riesgo de que el dato quede desactualizado? | bajo (siempre se pregunta el valor fresco) | existe, si el productor cambia ese dato después y no vuelve a emitir un evento |
| ¿De verdad desacopla en tiempo de ejecución a los dos módulos? | parcialmente — sigue habiendo una llamada de vuelta | sí, por completo |

**¿Qué usa este repositorio?** Se puede comprobar mirando exactamente qué
campos lleva cada evento y qué hace el que lo consume con ellos.

**`TrabajoCreado` → es un evento *gordo*.**

```python
@dataclass
class TrabajoCreado(EventoDominio):
    trabajo_id: uuid.UUID = None
    categoria: str = ''
    urgencia: str = ''
    pais: str = ''
    ciudad: str = ''
    canal: str = ''
    partner_id: str = ''
    estado: str = ''
```

Y la prueba de que es gordo **a propósito** está en cómo lo consume
`operaciones` (`modulos/operaciones/dominio/fabricas.py`):

```python
class FabricaSeguimientos(Fabrica):
    def crear_objeto(self, obj, mapeador=None) -> SeguimientoOperativo:
        seguimiento = SeguimientoOperativo(
            trabajo_id=str(obj.trabajo_id),
            pais=obj.pais,
            canal=obj.canal,
            categoria=obj.categoria,
            estado_trabajo=obj.estado,
            ventana_sla=POLITICA_SLA.get(obj.urgencia, POLITICA_SLA['NORMAL']),
        )
```

`operaciones` construye **todo** su `SeguimientoOperativo` — incluida la
prioridad del SLA, que depende de `urgencia` — leyendo directamente los
atributos del evento. **En ningún momento consulta la base de datos ni la API
del módulo `trabajos`.** Esto no es casualidad: es la única forma en que la
afirmación del README ("`operaciones` no importa una sola línea de
`trabajos`") es realmente cierta en tiempo de ejecución y no solo en tiempo
de compilación. Si `TrabajoCreado` fuera un evento flaco (solo `trabajo_id`),
`operaciones` tendría dos opciones, ambas peores: (a) hacerle un callback a
`trabajos` para pedir el resto de los datos —reintroduciendo el acoplamiento
en tiempo de ejecución que la arquitectura de eventos busca evitar—, o (b)
no poder calcular la prioridad del SLA en absoluto.

**`EstadoTrabajoCambiado` → un evento "delta", gordo *para lo que hace falta*, no un flaco puro.**

```python
@dataclass
class EstadoTrabajoCambiado(EventoDominio):
    trabajo_id: uuid.UUID = None
    estado_anterior: str = ''
    estado_nuevo: str = ''
```

No repite todo el snapshot del trabajo (no vuelve a mandar `pais`, `canal`,
`categoria`...), pero tampoco es un evento flaco puro (que solo diría "el
trabajo X cambió, ve a preguntar qué le pasó"): **sí** trae el dato que
cualquier consumidor necesitaría — el estado nuevo — así que
`operaciones` puede hacer `seguimiento.registrar_cambio_estado(evento.estado_nuevo)`
sin ninguna consulta adicional. Es un evento correctamente dimensionado: lleva
exactamente el delta que cambió, ni todo el agregado completo ni solo un id.

**`SubTrabajoAgregado` → el más flaco de los tres, y hoy sin consumidor.**

```python
@dataclass
class SubTrabajoAgregado(EventoDominio):
    trabajo_id: uuid.UUID = None
    sub_trabajo_id: uuid.UUID = None
    categoria: str = ''
```

Ningún handler de `operaciones` está suscrito a este evento todavía. Es un
buen ejemplo para explicar el límite del enfoque "gordo": si en el futuro
`operaciones` (o un tercer módulo) necesitara reaccionar a esto con más
contexto (la descripción del sub-trabajo, su estado inicial), habría que
**engordar el evento agregándole esos campos**, no agregar un callback.

**Los eventos de integración replican exactamente el mismo balance hacia
afuera.** En `infraestructura/schema/v1/eventos.py`,
`TrabajoCreadoPayload` copia los mismos ocho campos del evento de dominio
(gordo, para que otro microservicio tampoco tenga que llamar de vuelta a
Gestión de Trabajos), mientras que `EstadoTrabajoCambiadoPayload` solo
copia el delta (`trabajo_id`, `estado_anterior`, `estado_nuevo`).

**El costo que se acepta a cambio:** un evento gordo compromete más
superficie de contrato. Si mañana cambia qué significa `categoria` o se le
suman campos, hay más consumidores potencialmente afectados. Este repositorio
mitiga ese costo con lo que el propio código llama **tolerant reader**
(`infraestructura/schema/v1/eventos.py`, docstring): los eventos de
integración están versionados (`v1`, `v2`, ...) precisamente para poder
cambiar el contrato gordo sin romper a quien todavía no lo conoce — un
consumidor viejo simplemente ignora los campos que no reconoce.

---

## 8. Persistencia: Repositorio + Data Mapper

Un detalle que se nota poco pero es importante: las entidades de dominio
(`Trabajo`, `SubTrabajo`) **no tienen ni una sola anotación de SQLAlchemy**.
Los modelos de base de datos viven en un archivo aparte
(`infraestructura/dto.py`) que sí usa `Column`, `String`, `relationship`,
etc.

```python
# infraestructura/dto.py — esto SÍ sabe que existe una tabla SQL
class Trabajo(Base):
    __tablename__ = 'trabajos'
    id = Column(String(40), primary_key=True)
    ...
```

Entre uno y otro hay un **Mapeador** (`infraestructura/mapeadores.py`) cuyo
único trabajo es traducir de ida y vuelta:

```python
class RepositorioTrabajosPostgres(RepositorioTrabajos):
    def agregar(self, trabajo: Trabajo):
        db.session.add(self.mapeador.entidad_a_dto(trabajo))   # dominio -> fila SQL

    def obtener_por_id(self, id) -> Trabajo:
        registro = db.session.query(modelo.Trabajo)...
        return self.mapeador.dto_a_entidad(registro)           # fila SQL -> dominio
```

**¿Por qué separar esto en vez de anotar `Trabajo` directamente con
SQLAlchemy (como hacen muchos tutoriales)?** Porque si el modelo de dominio y
el modelo de base de datos son el mismo objeto, cualquier cambio de esquema
de base de datos (una columna nueva, una tabla dividida en dos) presiona
directamente sobre el dominio. Separándolos, el dominio cambia por razones de
**negocio**, y el modelo de persistencia cambia por razones de
**almacenamiento** — son dos motivos de cambio distintos, y por eso viven en
dos archivos distintos (principio de responsabilidad única, a nivel de
módulo).

---

## 9. Recorrido completo: qué pasa cuando llega `POST /trabajos`

Esta sección junta **todos** los patrones anteriores en una sola historia.
Es útil tenerla lista para explicar en vivo.

1. **Adaptador de entrada** (`api/trabajos.py`) recibe el JSON, arma un
   `Comando` `CrearTrabajo` y llama a `ejecutar_comando(comando)`. No sabe
   nada de dominio ni de base de datos — es CQS visible desde el borde del
   sistema.
2. `singledispatch` resuelve, por el tipo del comando, que debe llamar a
   `CrearTrabajoHandler`.
3. El handler pide a la **Fábrica** (`FabricaTrabajos`) que construya un
   `Trabajo` a partir del DTO recibido, usando un **Mapeador**.
4. El handler le pide al **Servicio de Dominio** (`SidecarReglasRegionales`,
   detrás del puerto `ServicioReglasRegionales`) qué categorías y urgencias
   aplican para el país del trabajo.
5. Se llama a `trabajo.crear(...)`. Ahí, la **agregación** valida sus
   **Reglas de negocio** (`UbicacionCompleta`, `CategoriaPermitidaEnRegion`,
   `UrgenciaPermitidaEnRegion`). Si alguna falla, se lanza
   `ReglaNegocioExcepcion` y el flujo se corta ahí — el `Trabajo` nunca llega
   a existir en un estado inválido.
6. Si todo es válido, la agregación cambia su propio estado a `CREADO` y
   **acumula** un evento de dominio `TrabajoCreado` en su lista interna de
   eventos. Todavía no se ha publicado nada ni se ha tocado la base de datos.
7. El handler pide el **Repositorio** (puerto) a través de una fábrica de
   infraestructura, y registra la operación `repositorio.agregar(trabajo)` en
   la **Unidad de Trabajo** — todavía sin ejecutarla.
8. El handler llama a `UnidadTrabajoPuerto.commit()`. Dentro de ese `commit`:
   a. Se ejecutan las operaciones pendientes (el `INSERT` real vía
      SQLAlchemy).
   b. Se hace el `commit()` real de la transacción SQL.
   c. **Solo si lo anterior tuvo éxito**, se publican los eventos de
      **integración**: `TrabajoCreado` sale hacia el tópico `evt-trabajo` de
      Pulsar, serializado en Avro.
9. En paralelo (dentro del mismo `registrar_batch`, antes del commit — ver
   paso 7), el evento de **dominio** ya había disparado, en memoria, al
   handler de `operaciones`, que construyó su propio `SeguimientoOperativo` y
   lo agregó **a la misma Unidad de Trabajo**. Por eso, si el `commit` falla,
   ni el `Trabajo` ni el `SeguimientoOperativo` quedan guardados.
10. La API responde `202 Accepted` con el `id` del trabajo — no con el
    trabajo completo, porque esto es un **Comando**, no una **Query**.

Para leer el resultado, el cliente hace `GET /trabajos/<id>` — una **Query**
completamente distinta, que no toca ninguna de las reglas anteriores, solo
lee.

---

## 10. Relación de cada criterio de la rúbrica con el código

| Criterio de la rúbrica | Evidencia concreta |
|---|---|
| Entidades, objetos valor, seedwork, servicios, módulos, agregaciones, fábricas, repositorios | Secciones 3.1 a 3.10 — cada una con archivo y código real |
| Arquitectura hexagonal (puertos y adaptadores) | Sección 4 — puertos en `dominio/`, adaptadores en `infraestructura/`, dos adaptadores de entrada distintos (HTTP y Pulsar) usando la misma capa de aplicación |
| Uso de un manejador de base de datos | Sección 8 — PostgreSQL vía SQLAlchemy, con Repositorio + Data Mapper separando dominio de persistencia |
| Comunicación entre módulos por eventos de dominio | Sección 7.1 — `trabajos` y `operaciones` se hablan exclusivamente por señales `pydispatch`, sin import cruzado |
| Diseño del contenido del evento (gordo vs. flaco) | Sección 7.5 — `TrabajoCreado` es gordo a propósito para que `operaciones` nunca necesite consultar a `trabajos`; se muestra el costo aceptado (más superficie de contrato) y cómo se mitiga (versionado `v1`, tolerant reader) |
| Patrón CQS (comandos y consultas) | Sección 5 — `Comando`/`ejecutar_comando` vs `Query`/`ejecutar_query`, reflejado incluso en los códigos de respuesta HTTP (`202` vs `200`) |

---

## 11. Limitaciones conocidas (para responder con honestidad si preguntan)

Ningún diseño es perfecto, y es mejor nombrar los límites que dejar que los
encuentre el evaluador:

1. **La regla "el dominio no importa infraestructura" no se hace cumplir con
   una prueba automática de arquitectura** — hoy depende de disciplina y
   revisión de código.
2. **El sidecar regional corre en el mismo proceso** (lee un JSON local) en
   vez de ser un servicio desplegado aparte; el puerto ya existe, así que
   cambiarlo por un adaptador HTTP real no tocaría el dominio.
3. **El consumidor de comandos no es idempotente** — un reintento del broker
   podría crear un trabajo duplicado.
4. **La cobertura de pruebas se concentra en el dominio puro**
   (`tests/test_dominio_trabajo.py`); falta una prueba de integración que
   verifique el recorrido completo de la sección 9 (comando → evento de
   dominio → módulo `operaciones` → evento de integración).

---

## 12. Glosario exprés (para repasar 5 minutos antes de sustentar)

- **Entidad**: objeto con identidad propia; importa quién es.
- **Objeto Valor**: objeto inmutable sin identidad; importa lo que vale.
- **Agregado**: grupo de objetos que deben cambiar de forma consistente,
  accesible solo a través de su raíz.
- **Raíz de Agregado**: la única puerta de entrada a un agregado.
- **Fábrica**: encapsula la construcción de objetos complejos y garantiza que
  nazcan válidos.
- **Repositorio**: puerto para guardar/leer agregados sin saber qué
  tecnología hay detrás.
- **Servicio de Dominio**: lógica de negocio que no encaja naturalmente en
  ninguna entidad.
- **Regla de negocio / Especificación**: una condición de negocio convertida
  en objeto, con un método `es_valido()`.
- **Evento de dominio**: un hecho ya ocurrido, contado en pasado, usado para
  comunicar entre partes del sistema sin acoplarlas.
- **Evento de integración**: la versión de un evento de dominio pensada para
  salir del servicio hacia el resto del sistema.
- **Evento flaco / ligero** (*event notification*): lleva solo un
  identificador; el consumidor debe llamar de vuelta al productor para
  obtener el resto de los datos.
- **Evento gordo** (*event-carried state transfer*): lleva copiado todo el
  contexto necesario para que el consumidor actúe sin preguntarle nada de
  vuelta al productor. `TrabajoCreado` es el ejemplo de este repositorio.
- **Puerto**: una interfaz definida desde el punto de vista del dominio.
- **Adaptador**: una implementación concreta de un puerto, atada a una
  tecnología específica.
- **CQS**: separar las operaciones que cambian estado (comandos) de las que
  solo leen (consultas).
- **Unidad de Trabajo**: agrupa varias operaciones para que se confirmen
  todas juntas o ninguna.
- **Bounded Context / Módulo**: una zona del sistema con su propio
  vocabulario y sus propias reglas, con límites explícitos frente a otras
  zonas.
- **Seedwork**: conjunto de piezas base de DDD, copiado (no compartido) entre
  microservicios para evitar acoplamiento en tiempo de compilación.
