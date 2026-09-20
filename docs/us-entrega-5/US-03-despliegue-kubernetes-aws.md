# US-03 · Despliegue del sistema en Kubernetes sobre AWS

| Campo | Valor |
|---|---|
| **Entrega** | 5 |
| **Actividad del enunciado** | (c) Añadir la opción de desplegar en Kubernetes sobre AWS |
| **Alcance** | **Todo** dentro del clúster: los seis servicios, las cinco bases de datos y el clúster de Pulsar |
| **Qué NO cambia** | El despliegue actual con Docker Compose sigue funcionando exactamente igual |
| **Estado** | Propuesta — pendiente de aprobación |

---

## La historia

> **Como** equipo responsable de Hogar de los Alpes,
> **queremos** poder desplegar el sistema completo en un clúster de Kubernetes
> en AWS con un procedimiento repetible,
> **para** poder probarlo en condiciones parecidas a las de producción —con
> almacenamiento persistente de verdad, varios nodos, y componentes que se
> recuperan solos cuando se caen— en lugar de solo en la máquina de alguien.
>
> **Y queremos** conservar el despliegue actual con Docker Compose,
> **para** no perder la forma rápida de trabajar en el día a día ni la evidencia
> que ya produjeron los escenarios de calidad de la entrega anterior.

---

## Por qué esta historia existe

Hoy el sistema se despliega de una sola forma: `docker compose up` sobre una
máquina, sea el portátil de alguien o una instancia EC2. Eso tiene una ventaja
real —lo que se prueba en local es literalmente lo mismo que corre en la nube— y
dos límites que ya no se pueden ignorar:

1. **Todo vive en una sola máquina.** Si esa máquina se cae, se cae el sistema
   entero. Las promesas de disponibilidad del proyecto se demuestran deteniendo
   un contenedor, no sobreviviendo a la pérdida de un nodo.
2. **Nada se recupera solo.** Si un proceso muere, alguien tiene que
   levantarlo. En producción eso no es aceptable.

Kubernetes resuelve las dos: reparte los componentes entre varios nodos y
reinicia solo lo que se cae. Esta historia agrega esa opción **sin quitar la que
ya existe**.

---

## Qué se va a desplegar

Con la saga (US-01) y el BFF (US-02), el sistema pasa a tener **seis servicios**
y **cinco bases de datos**, más el clúster de mensajería. En Kubernetes eso se
traduce en:

### Los procesos de aplicación

| Componente | Copias iniciales | Tiene API HTTP |
|---|---|---|
| Gestión de Trabajos — API | 2 | Sí |
| Gestión de Trabajos — consumidor | 1 | No |
| Operaciones — API | 1 | Sí |
| Operaciones — consumidor | 1 | No |
| Acreditación — API | 1 | Sí |
| Acreditación — consumidor | 1 | No |
| Emparejamiento — API | 2 | Sí |
| Emparejamiento — consumidor de proyección | 1 | No |
| Emparejamiento — consumidor por región (andina, norteamérica) | 1 cada uno | No |
| Registro de sagas — API | 1 | Sí |
| Registro de sagas — consumidor | 1 | No |
| **BFF** | 2 | Sí — es el único expuesto hacia afuera |

### Lo que necesita almacenamiento que sobreviva

| Componente | Copias | Por qué necesita disco propio |
|---|---|---|
| PostgreSQL × 5 (una por servicio con datos) | 1 cada una | Cada servicio tiene su propia base, y eso no cambia |
| ZooKeeper | 1 | Guarda los metadatos del clúster de mensajería |
| Bookies (el almacén durable de Pulsar) | 2 | Son los que garantizan que un mensaje no se pierda. **Este es el componente más delicado de toda la historia** |
| Brokers de Pulsar | 2 | No guardan datos, pero reparten las particiones |

### Las tareas de preparación

El guion que crea el tenant, los espacios de nombres, las políticas, los tópicos
y las suscripciones **ya existe y ya es repetible** (se puede correr dos veces
sin romper nada). En Kubernetes se ejecuta como una tarea que corre una sola vez
después de que los brokers estén sanos, igual que hoy corre después de ellos en
Compose. **No hay que reescribirlo.**

---

## Las cinco decisiones técnicas que definen esta historia

### 1. Las imágenes tienen que publicarse en un registro

Hoy Docker Compose construye las imágenes en el momento, a partir del código.
Kubernetes no puede hacer eso: necesita descargar una imagen ya construida de
algún lado. Se publican en el registro de contenedores de AWS, etiquetadas con
la versión del código, de modo que siempre se sepa exactamente qué versión está
corriendo.

**Es un cambio de forma de trabajar, no solo un archivo más:** a partir de aquí,
desplegar deja de ser «construir y levantar» y pasa a ser «construir, publicar y
desplegar».

### 2. El aislamiento entre servicios hay que volver a garantizarlo — no viene gratis

Esta es la parte más importante de la historia y la más fácil de pasar por alto.

Hoy, el proyecto puede afirmar algo fuerte: *«Gestión de Trabajos no puede leer
la base de datos de Acreditación, porque no hay ruta de red entre ellos»*. Eso no
es disciplina del equipo, es una imposibilidad física creada por las redes
separadas de Docker. Es una de las afirmaciones más sólidas de la Entrega 4.

**En Kubernetes, por defecto, todos los componentes pueden hablar con todos.** Si
se traducen los archivos tal cual, esa garantía **se pierde en silencio**: nada
falla, nada avisa, y la afirmación deja de ser cierta sin que nadie se entere.

Para conservarla hay que declarar explícitamente las reglas de conexión
permitidas —quién puede hablar con quién— y verificar que se están aplicando de
verdad. Esto exige además que el clúster tenga habilitado el componente de red
que hace cumplir esas reglas; si no, se declaran pero no se aplican, que es el
peor de los dos mundos.

> **Si esta historia se entrega sin esta parte verificada, el sistema en
> Kubernetes es arquitectónicamente más débil que el sistema en Compose.**

### 3. Las reglas regionales pasan de archivo montado a configuración del clúster

Hoy, agregar un país es editar un archivo que está montado dentro del
contenedor y reiniciar el proceso: cero cambios de código, sin reconstruir la
imagen. Esa propiedad es uno de los escenarios de calidad del proyecto y **no se
puede perder**.

En Kubernetes el equivalente natural es guardar ese mismo archivo como
configuración del clúster y montarlo igual. Agregar un país sigue siendo: editar
la configuración y reiniciar el proceso. La propiedad se conserva, cambia la
forma de guardar el archivo.

### 4. Las contraseñas se generan al desplegar, nunca se guardan en el repositorio

Igual que hoy: el repositorio es público y no lleva ninguna credencial. Las
contraseñas de las bases de datos se generan en el momento del despliegue y se
guardan como secretos del clúster.

### 5. Los guiones de escenarios necesitan una variante

Los guiones que demuestran los escenarios de calidad detienen y escalan
contenedores con comandos de Docker Compose. En Kubernetes esos comandos son
otros. Se agrega la variante correspondiente, **sin borrar la existente**: cada
guion sabe contra cuál de los dos entornos está corriendo.

| Escenario | En Compose | En Kubernetes |
|---|---|---|
| Disponibilidad — detener el reactor | detener el contenedor consumidor | bajar a cero las copias de ese consumidor |
| Escalabilidad — más copias | escalar el servicio | escalar las copias del consumidor |
| Escalabilidad — región nueva en caliente | correr el guion de alta de región | correr el mismo guion como tarea + desplegar el consumidor de esa región |
| Modificabilidad — país nuevo | editar el archivo montado y reiniciar | editar la configuración y reiniciar |
| Modificabilidad — adaptador de persistencia | cambiar una variable y reiniciar | cambiar la variable del despliegue y reiniciar |

---

## Cómo queda organizado en el repositorio

```
infra/
├── aws/
│   ├── terraform/          lo que ya existe: la instancia EC2 con Compose
│   └── terraform-eks/      NUEVO: el clúster de Kubernetes y sus nodos
└── k8s/                    NUEVO: la descripción de todo lo que va adentro
    ├── pulsar/             zookeeper, bookies, brokers, tarea de preparación
    ├── bases-de-datos/     las cinco bases de datos
    ├── servicios/          los seis servicios (API y consumidores)
    ├── configuracion/      reglas regionales y variables comunes
    ├── red/                las reglas de quién puede hablar con quién
    └── entornos/           las diferencias entre un entorno pequeño y uno completo
```

Y el procedimiento completo, paso a paso y verificado de principio a fin, en
`infra/k8s/README.md`.

---

## Criterios de aceptación

### El despliegue funciona

- [ ] **CA-3.1** — Desde una cuenta de AWS limpia, siguiendo el `README` al pie
      de la letra, se llega a un sistema completo funcionando. **El
      procedimiento se ejecuta de verdad, no solo se escribe.**
- [ ] **CA-3.2** — Los seis servicios, las cinco bases de datos y el clúster de
      Pulsar quedan sanos dentro del clúster.
- [ ] **CA-3.3** — El BFF queda accesible desde fuera del clúster por una única
      dirección, y desde ahí se puede usar todo el sistema.
- [ ] **CA-3.4** — La colección de Postman del BFF corre en verde contra esa
      dirección, con solo cambiar el entorno.
- [ ] **CA-3.5** — El clúster de Pulsar tiene sus **dos** brokers y sus **dos**
      almacenes durables activos, y la preparación de tópicos y suscripciones
      quedó aplicada — verificado consultando el propio clúster, no suponiéndolo
      porque el comando no protestó.
- [ ] **CA-3.6** — El despliegue completo se puede hacer con **un solo comando**
      una vez que el clúster existe.
- [ ] **CA-3.7** — Todo el despliegue se puede **destruir con un solo comando**,
      sin dejar recursos cobrando.

### Lo que ya funcionaba sigue funcionando

- [ ] **CA-3.8** — **`docker compose up` sigue levantando el sistema completo
      exactamente igual que antes de esta historia.** Es un criterio duro: si se
      rompe, la historia no está terminada.
- [ ] **CA-3.9** — Los cinco escenarios de calidad de la Entrega 4 se pueden
      ejecutar en Kubernetes y dan resultados comparables a los de Compose. Las
      diferencias que aparezcan se explican y se documentan, no se esconden.
- [ ] **CA-3.10** — La saga de US-01 funciona igual en Kubernetes: caso exitoso y
      los tres casos de fallo con su compensación completa.
- [ ] **CA-3.10b** — **La trazabilidad por identificador de correlación sigue
      funcionando entre procesos separados.** Buscar un identificador en los
      registros del clúster devuelve la cadena completa de la petición, igual que
      en Compose. En Kubernetes los procesos están en máquinas distintas, así que
      el `README` explica con qué comando se consultan los registros de varios
      procesos a la vez.

### Aislamiento y seguridad

- [ ] **CA-3.11** — **Ningún servicio puede alcanzar la base de datos de otro.**
      Se verifica con la misma comprobación que ya existe hoy: desde dentro de un
      servicio, intentar conectarse a una base ajena debe fallar. Son las mismas
      nueve comprobaciones que la Entrega 4 ya documentó, repetidas en el clúster.
- [ ] **CA-3.12** — **Ningún servicio de dominio puede alcanzar a otro servicio
      de dominio por HTTP.** Solo el BFF alcanza a los seis, y solo hacia adentro.
- [ ] **CA-3.13** — Las reglas de red se están aplicando de verdad: se comprueba
      que una conexión prohibida **efectivamente falla**, no solo que la regla
      está escrita.
- [ ] **CA-3.14** — Las bases de datos y el clúster de mensajería **no están
      expuestos hacia internet**. Solo el BFF lo está.
- [ ] **CA-3.15** — El repositorio no contiene ninguna credencial, ninguna
      dirección de la cuenta de AWS ni ningún dato del clúster real.

### Persistencia y recuperación

- [ ] **CA-3.16** — Si se elimina el proceso de un servicio, el clúster lo vuelve
      a levantar solo y el sistema sigue respondiendo.
- [ ] **CA-3.17** — Si se elimina el proceso de una base de datos, al volver
      **conserva sus datos**.
- [ ] **CA-3.18** — Si se elimina un almacén durable de Pulsar, al volver
      conserva los mensajes y ninguna suscripción pierde su posición.
- [ ] **CA-3.19** — Ninguna base de datos ni componente de mensajería guarda sus
      datos dentro del contenedor: todos usan almacenamiento que sobrevive al
      reinicio.

### Los escenarios de calidad, traducidos

- [ ] **CA-3.20** — **Disponibilidad:** bajar a cero el consumidor de
      Operaciones hace crecer su acumulado de mensajes pendientes sin afectar a
      Gestión de Trabajos; al volver a levantarlo, procesa el 100% sin duplicar.
- [ ] **CA-3.21** — **Escalabilidad:** duplicar las copias de un consumidor casi
      duplica su velocidad de procesamiento, con la misma medida que usa el
      escenario actual.
- [ ] **CA-3.22** — **Región nueva en caliente:** agregar una región no
      interrumpe a las que ya estaban activas.
- [ ] **CA-3.23** — **País nuevo:** agregar un país editando la configuración del
      clúster y reiniciando el proceso funciona **sin reconstruir ni volver a
      publicar ninguna imagen**. Cero archivos de código modificados.
- [ ] **CA-3.24** — **Adaptador de persistencia:** cambiar la variable que elige
      cómo guarda sus datos Gestión de Trabajos funciona igual que en Compose.
- [ ] **CA-3.25** — **Estado nuevo:** redesplegar únicamente Gestión de Trabajos
      no reinicia a los demás servicios, y ellos procesan el estado nuevo sin
      enterarse de antemano.

### Documentación y costo

- [ ] **CA-3.26** — `infra/k8s/README.md` explica el procedimiento completo —
      requisitos previos, cómo crear el clúster, cómo publicar las imágenes,
      cómo desplegar, cómo verificar y cómo destruir — con los comandos exactos.
- [ ] **CA-3.27** — Está documentado el **costo aproximado por hora y por día**,
      y cómo dejar de pagar cuando no se está usando.
- [ ] **CA-3.28** — El `README.md` del proyecto explica que hay **dos formas** de
      desplegar y cuándo conviene cada una.
- [ ] **CA-3.29** — Si el entorno de AWS del curso no permite alguno de los
      recursos necesarios, la limitación y su alternativa quedan documentadas —
      no se deja como «no se pudo».

---

## Lo que **no** entra en esta historia

- **No se retira el despliegue con Docker Compose**, ni el que ya existe sobre
  una instancia EC2. Son tres caminos, y los tres se mantienen.
- **No se usa una base de datos gestionada** (tipo RDS) ni un Pulsar
  contratado. La regla del curso es que el equipo configura y despliega su
  propio clúster de mensajería, y esa regla no cambia porque cambie la
  plataforma.
- **No hay escalado automático por carga.** El número de copias se cambia a
  mano, que es justamente lo que el escenario de escalabilidad mide.
- **No hay despliegue automático desde el repositorio** (integración continua).
  El despliegue se dispara a mano.
- **No hay múltiples entornos** (desarrollo, pruebas, producción). Hay un
  entorno, con la posibilidad de levantarlo en tamaño reducido o completo.
- **No hay múltiples zonas ni recuperación ante desastres.**
- **No se agregan tableros de monitoreo nuevos.** Los que ya existen se
  despliegan si caben; si no, se documenta cómo consultar el estado a mano.

---

## Riesgos y cosas que hay que tener en cuenta

| # | Riesgo | Por qué importa | Cómo se maneja |
|---|---|---|---|
| R5-11 | **Pulsar con almacenamiento persistente en Kubernetes es la parte más difícil.** El plan técnico de la Entrega 4 ya había descartado Kubernetes en su momento precisamente por esto | Los almacenes durables necesitan disco propio que sobreviva. Si se configuran mal, se pierden mensajes — y eso rompe la promesa central del sistema | Se ataca **primero**, antes que cualquier otra cosa. Si a las cuatro horas no funciona, se aplica el plan alterno: reducir el clúster de mensajería a una configuración más simple dentro de Kubernetes y documentar la reducción |
| R5-12 | **Perder el aislamiento de red sin darse cuenta** | En Kubernetes todo se habla con todo por defecto. Si nadie lo restringe, el sistema desplegado contradice lo que la documentación afirma, y nada avisa | Es el criterio CA-3.13: la verificación **prueba que una conexión prohibida falla**, no que la regla existe |
| R5-13 | **El entorno de AWS del curso puede no permitir lo que se necesita** | Las cuentas educativas suelen tener límites de tipos de máquina, de cantidad de nodos y de servicios habilitados | Se verifica **el primer día**, no al final. Si algo no se permite, se documenta con su alternativa (CA-3.29) |
| R5-14 | **El costo.** Un clúster de Kubernetes cobra por existir, aparte de las máquinas | Con más de veinte procesos, cinco bases de datos y el clúster de mensajería, el gasto diario no es despreciable | Se levanta solo para probar y para la sustentación, y se destruye después. El costo queda documentado (CA-3.27) |
| R5-15 | **Publicar imágenes es un paso nuevo que se puede olvidar** | Desplegar código viejo sin darse cuenta es una forma silenciosa de perder una tarde | Las imágenes se etiquetan con la versión del código, nunca con una etiqueta genérica, y la verificación incluye confirmar qué versión está corriendo |
| R5-16 | **Los procesos consumidores no tienen API**, así que no se les puede preguntar si están sanos de la forma habitual | El clúster podría dar por sano un consumidor que en realidad no está consumiendo | Se define para ellos una comprobación de salud distinta, y se verifica que un consumidor colgado efectivamente se detecta |
| R5-17 | **Las mediciones en Kubernetes pueden dar distinto** que en Compose, porque los componentes están en máquinas diferentes y la red pasa por el medio | Comparar números de dos entornos distintos sin advertirlo sería engañoso | Las mediciones de cada entorno se reportan por separado, con su contexto. No se mezclan en una sola tabla |

---

## Orden de trabajo sugerido

El orden importa: la parte más riesgosa va primero, para que si falla haya
tiempo de reaccionar en lugar de descubrirlo el último día.

| # | Paso | Por qué en este punto |
|---|---|---|
| 1 | Verificar qué permite la cuenta de AWS del curso | Si hay un límite bloqueante, cambia todo el plan |
| 2 | Crear el clúster vacío y publicar una imagen de prueba | Valida la cadena completa antes de meter complejidad |
| 3 | **Pulsar con almacenamiento persistente** | Es el riesgo mayor. Se resuelve o se aplica el plan alterno |
| 4 | Las cinco bases de datos | Mismo mecanismo de almacenamiento, ya probado en el paso 3 |
| 5 | Los seis servicios y el BFF | Es la parte mecánica: ya no hay incógnitas |
| 6 | Las reglas de red y su verificación | Antes de declarar nada terminado |
| 7 | Variante de los guiones de escenarios y corrida completa | La evidencia para la sustentación |
| 8 | Documentación, costos y procedimiento verificado de punta a punta | Que otra persona pueda repetirlo |

---

## Definición de terminado

- [ ] Los treinta criterios de aceptación se cumplen y están verificados.
- [ ] Alguien que **no participó** en la historia levanta el sistema completo
      siguiendo solo el `README`, y lo consigue.
- [ ] Los resultados de los escenarios corridos en Kubernetes quedan guardados
      en `docs/resultados/`, identificados como tales.
- [ ] El clúster se destruye después de la verificación, y queda constancia de
      que destruirlo también funciona.
- [ ] Las decisiones y los tropiezos quedan anotados en `docs/decisiones.md`,
      con el mismo estilo honesto del resto del documento: **lo que se verificó
      se marca como verificado, y lo que quedó pendiente se marca como
      pendiente.**
- [ ] `docs/actividades.md` registra quién hizo qué, con enlaces a sus *commits*
      y a su *pull request*.
