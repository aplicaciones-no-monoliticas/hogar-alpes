# Feature Specification: Despliegue del sistema en Kubernetes sobre AWS

**Feature Branch**: `003-despliegue-kubernetes-aws`

**Created**: 2026-09-21

**Status**: Draft

**Input**: User description: "@docs/us-entrega-5/US-03-despliegue-kubernetes-aws.md"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Desplegar el sistema completo en Kubernetes desde cero (Priority: P1)

Como equipo responsable de Hogar de los Alpes, quiero poder levantar el sistema completo
(seis servicios, cinco bases de datos y el clúster de mensajería) en un clúster de Kubernetes
sobre AWS siguiendo un procedimiento documentado y repetible, para poder probarlo en
condiciones parecidas a producción —varios nodos, almacenamiento persistente real, y
recuperación automática ante fallas— en vez de solo en la máquina de una persona.

**Why this priority**: Es el objetivo central de la historia. Sin esto no existe la opción de
despliegue en Kubernetes, y ningún otro criterio de aceptación se puede verificar.

**Independent Test**: Desde una cuenta de AWS limpia, siguiendo únicamente el procedimiento
documentado, se llega a un sistema completo funcionando: los seis servicios, las cinco bases
de datos y el clúster de Pulsar quedan sanos, y el BFF responde desde una única dirección
accesible desde fuera del clúster.

**Acceptance Scenarios**:

1. **Given** una cuenta de AWS limpia y el procedimiento documentado, **When** se sigue el
   procedimiento paso a paso, **Then** el sistema completo queda desplegado y funcionando sin
   pasos manuales fuera de lo documentado.
2. **Given** el clúster ya desplegado, **When** se consulta el estado de los seis servicios,
   las cinco bases de datos y el clúster de Pulsar, **Then** todos aparecen sanos.
3. **Given** el sistema desplegado, **When** se accede al BFF por su dirección pública única,
   **Then** se puede usar todo el sistema a través de él, y la colección de Postman del BFF
   corre en verde contra esa dirección cambiando solo el entorno.
4. **Given** el clúster desplegado, **When** se ejecuta el comando único de despliegue sobre un
   clúster ya existente, **Then** el sistema completo queda desplegado sin pasos adicionales.
5. **Given** un despliegue activo, **When** se ejecuta el comando único de destrucción,
   **Then** no queda ningún recurso del sistema cobrando en la cuenta de AWS.

---

### User Story 2 - Conservar el aislamiento de red entre servicios (Priority: P1)

Como equipo responsable de Hogar de los Alpes, quiero que en Kubernetes se mantenga la misma
garantía que existe hoy en Docker Compose —que un servicio no puede alcanzar la base de datos
ni la API de otro servicio de dominio salvo a través del BFF—, para que el sistema desplegado
en Kubernetes no sea arquitectónicamente más débil que el sistema en Compose.

**Why this priority**: Es la parte más fácil de perder en silencio (en Kubernetes todo se habla
con todo por defecto) y una de las afirmaciones más sólidas del proyecto. Si se pierde, nada
falla visiblemente, pero la garantía deja de ser cierta.

**Independent Test**: Desde dentro de un servicio de dominio desplegado en el clúster, intentar
conectarse a la base de datos de otro servicio y a la API de otro servicio de dominio; ambos
intentos deben fallar de forma verificable (no solo "la regla existe", sino "la conexión
efectivamente no pasa").

**Acceptance Scenarios**:

1. **Given** el sistema desplegado en Kubernetes, **When** un servicio intenta conectarse a la
   base de datos de otro servicio, **Then** la conexión falla, repitiendo las mismas nueve
   comprobaciones ya documentadas para Compose.
2. **Given** el sistema desplegado en Kubernetes, **When** un servicio de dominio intenta
   alcanzar por HTTP a otro servicio de dominio (no al BFF), **Then** la conexión falla.
3. **Given** las reglas de red declaradas, **When** se verifica su aplicación, **Then** se
   comprueba que una conexión prohibida efectivamente falla, no solo que la regla está escrita.
4. **Given** el sistema desplegado, **When** se intenta alcanzar una base de datos o el clúster
   de mensajería directamente desde fuera del clúster, **Then** el intento falla; solo el BFF
   es alcanzable desde fuera.

---

### User Story 3 - Persistencia y auto-recuperación ante fallas (Priority: P1)

Como equipo responsable de Hogar de los Alpes, quiero que si un proceso, una base de datos o un
almacén durable de Pulsar se cae dentro del clúster, el sistema se recupere solo y sin pérdida
de datos, para demostrar las promesas de disponibilidad del proyecto sobreviviendo a la pérdida
de un componente en vez de solo deteniendo un contenedor.

**Why this priority**: Es la razón de negocio declarada para esta historia (hoy nada se
recupera solo y todo vive en una máquina). Sin esto, Kubernetes no aporta nada sobre Compose.

**Independent Test**: Eliminar el proceso de un servicio, de una base de datos y de un almacén
durable de Pulsar por separado, y verificar en cada caso que el componente vuelve a levantarse
solo, conserva sus datos/mensajes, y el sistema sigue respondiendo.

**Acceptance Scenarios**:

1. **Given** el sistema desplegado, **When** se elimina el proceso de un servicio, **Then** el
   clúster lo vuelve a levantar sin intervención manual y el sistema sigue respondiendo.
2. **Given** el sistema desplegado, **When** se elimina el proceso de una base de datos,
   **Then** al volver a levantarse conserva todos sus datos previos.
3. **Given** el sistema desplegado, **When** se elimina un almacén durable de Pulsar,
   **Then** al volver conserva los mensajes ya publicados y ninguna suscripción pierde su
   posición de lectura.
4. **Given** cualquier base de datos o componente de mensajería del sistema, **When** se
   inspecciona su almacenamiento, **Then** ninguno guarda datos dentro del contenedor; todos
   usan almacenamiento que sobrevive al reinicio del proceso.

---

### User Story 4 - Los escenarios de calidad de la Entrega 4 funcionan igual en Kubernetes (Priority: P2)

Como equipo responsable de Hogar de los Alpes, quiero poder ejecutar en Kubernetes los mismos
escenarios de calidad ya demostrados en Docker Compose (disponibilidad, escalabilidad, región
nueva en caliente, país nuevo, adaptador de persistencia) y obtener resultados comparables,
para no perder la evidencia que ya se produjo en la entrega anterior.

**Why this priority**: Depende de que las historias 1-3 ya funcionen; es la demostración de que
el nuevo entorno preserva las propiedades ya probadas, pero no bloquea la existencia del
despliegue en sí.

**Independent Test**: Ejecutar cada uno de los cinco guiones de escenarios en su variante de
Kubernetes contra el sistema desplegado y comparar el resultado contra el ya documentado para
Compose, registrando explícitamente cualquier diferencia.

**Acceptance Scenarios**:

1. **Given** el consumidor de Operaciones desplegado, **When** se bajan sus copias a cero,
   **Then** su acumulado de mensajes pendientes crece sin afectar a Gestión de Trabajos, y al
   volver a levantarlo procesa el 100% de lo acumulado sin duplicar.
2. **Given** un consumidor con una copia activa, **When** se duplican sus copias, **Then** su
   velocidad de procesamiento casi se duplica, medida con el mismo método que usa el escenario
   ya existente.
3. **Given** el sistema desplegado con las regiones ya activas, **When** se agrega una región
   nueva en caliente (guion de alta de región + despliegue del consumidor de esa región),
   **Then** las regiones que ya estaban activas no se interrumpen.
4. **Given** el sistema desplegado, **When** se agrega un país nuevo editando la configuración
   del clúster y reiniciando el proceso correspondiente, **Then** el cambio surte efecto sin
   reconstruir ni volver a publicar ninguna imagen y sin modificar ningún archivo de código.
5. **Given** el sistema desplegado, **When** se cambia la variable que elige el adaptador de
   persistencia de Gestión de Trabajos, **Then** el comportamiento resultante es equivalente al
   que se obtiene haciendo el mismo cambio en Compose.
6. **Given** el sistema desplegado, **When** se redespliega únicamente Gestión de Trabajos con
   soporte para un estado nuevo, **Then** los demás servicios no se reinician y procesan el
   estado nuevo sin haber sido notificados de antemano.

---

### User Story 5 - Convivencia con el despliegue existente en Docker Compose (Priority: P1)

Como equipo responsable de Hogar de los Alpes, quiero conservar el despliegue actual con Docker
Compose funcionando exactamente igual que antes, para no perder la forma rápida de trabajar en
el día a día ni la evidencia que ya produjeron los escenarios de calidad de la entrega anterior.

**Why this priority**: Es un criterio duro explícito de la historia: si se rompe, la historia no
está terminada, sin importar qué tan bien funcione la parte de Kubernetes.

**Independent Test**: Ejecutar el comando de arranque de Docker Compose en un checkout limpio
después de todos los cambios de esta historia y confirmar que el sistema completo se levanta
exactamente igual que antes de la historia.

**Acceptance Scenarios**:

1. **Given** el repositorio con todos los cambios de esta historia, **When** se levanta el
   sistema con el comando de Docker Compose ya existente, **Then** el sistema completo queda
   funcionando exactamente igual que antes de esta historia.
2. **Given** las dos formas de despliegue disponibles, **When** alguien consulta la
   documentación principal del proyecto, **Then** encuentra explicado que existen dos formas de
   desplegar y cuándo conviene usar cada una.

---

### Edge Cases

- ¿Qué pasa si la cuenta de AWS del curso no permite alguno de los tipos de nodo, cantidad de
  nodos o servicios que el despliegue necesita? → La limitación y su alternativa deben quedar
  documentadas explícitamente, nunca reportadas como "no se pudo".
- ¿Qué pasa si el almacenamiento persistente de los almacenes durables de Pulsar no se puede
  configurar de forma confiable en el tiempo disponible? → Se aplica el plan alterno: reducir el
  clúster de mensajería a una configuración más simple dentro de Kubernetes, documentando
  explícitamente la reducción y su impacto.
- ¿Cómo se verifica la salud de un proceso consumidor, que no expone una API HTTP a la que
  preguntar? → Se define una comprobación de salud distinta para estos procesos, y se verifica
  que un consumidor colgado (que dejó de consumir pero no terminó el proceso) efectivamente se
  detecta como no sano.
- ¿Qué pasa si alguien intenta comparar directamente una medición de un escenario de calidad
  hecha en Compose contra la misma medición hecha en Kubernetes? → Los resultados de cada
  entorno se reportan por separado con su propio contexto; no se combinan en una sola tabla,
  porque la topología de red entre procesos es distinta y los números no son comparables sin
  advertencia.
- ¿Qué pasa si se publica una nueva versión del código pero se olvida publicar y desplegar la
  imagen correspondiente? → El procedimiento de verificación incluye confirmar qué versión de
  cada imagen está efectivamente corriendo en el clúster, no solo que el despliegue no reportó
  error.
- ¿Qué pasa si alguien reconstruye los manifiestos de Kubernetes traduciendo literalmente los
  archivos de Docker Compose sin declarar reglas de red? → Por defecto todos los componentes
  podrían hablarse entre sí; este es precisamente el riesgo que las historias 2 y sus criterios
  de verificación (conexión prohibida que efectivamente falla) existen para detectar.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST poder desplegarse completo (seis servicios de aplicación, cinco
  bases de datos y el clúster de mensajería) dentro de un clúster de Kubernetes en AWS, con un
  procedimiento documentado que otra persona pueda seguir sin haber participado en la historia.
- **FR-002**: El despliegue completo del sistema sobre un clúster de Kubernetes ya existente
  MUST poder ejecutarse con un único comando.
- **FR-003**: El despliegue completo MUST poder destruirse con un único comando, sin dejar
  recursos de la cuenta de AWS cobrando después.
- **FR-004**: Las imágenes de los seis servicios MUST publicarse en un registro de contenedores
  antes de desplegarse, etiquetadas de forma que siempre se pueda saber exactamente qué versión
  del código está corriendo en el clúster.
- **FR-005**: El BFF MUST ser el único componente del sistema accesible desde fuera del
  clúster, alcanzable por una única dirección, y desde ahí MUST poder usarse el sistema
  completo.
- **FR-006**: La colección de Postman del BFF MUST poder ejecutarse en verde contra el sistema
  desplegado en Kubernetes cambiando únicamente el entorno de la colección.
- **FR-007**: El clúster de mensajería MUST desplegarse con sus dos brokers y sus dos almacenes
  durables activos, y la preparación de tenant, espacios de nombres, políticas, tópicos y
  suscripciones MUST quedar aplicada, verificándolo contra el propio clúster (no asumiéndolo
  porque el comando de preparación no reportó error).
- **FR-008**: Ningún servicio de dominio MUST poder alcanzar la base de datos de otro servicio
  de dominio dentro del clúster.
- **FR-009**: Ningún servicio de dominio MUST poder alcanzar a otro servicio de dominio por HTTP
  dentro del clúster; solo el BFF MUST poder alcanzarlos, y únicamente hacia ellos.
- **FR-010**: Las reglas de red que imponen los requisitos FR-008 y FR-009 MUST verificarse
  demostrando que una conexión prohibida efectivamente falla, no solo que la regla está
  declarada.
- **FR-011**: Ninguna base de datos ni el clúster de mensajería MUST estar expuesto hacia
  internet; únicamente el BFF MUST estarlo.
- **FR-012**: El repositorio MUST NOT contener ninguna credencial, ninguna dirección de la
  cuenta de AWS real ni ningún dato del clúster real; las contraseñas de las bases de datos
  MUST generarse en el momento del despliegue y guardarse como secretos del clúster.
- **FR-013**: Si el proceso de un servicio se elimina dentro del clúster, el sistema MUST
  volver a levantarlo automáticamente y seguir respondiendo, sin intervención manual.
- **FR-014**: Si el proceso de una base de datos se elimina dentro del clúster, al volver a
  levantarse MUST conservar todos sus datos previos.
- **FR-015**: Si un almacén durable de Pulsar se elimina dentro del clúster, al volver MUST
  conservar los mensajes ya publicados y ninguna suscripción MUST perder su posición de
  lectura.
- **FR-016**: Ninguna base de datos ni componente de mensajería MUST guardar sus datos dentro
  del contenedor; todos MUST usar almacenamiento que sobreviva al reinicio del proceso.
- **FR-017**: Las reglas regionales (categorías y urgencias permitidas por país) MUST poder
  editarse como configuración del clúster, y ese cambio MUST surtir efecto reiniciando
  únicamente el proceso correspondiente, sin modificar código ni reconstruir ninguna imagen.
- **FR-018**: Cada uno de los cinco escenarios de calidad ya existentes para Docker Compose
  (disponibilidad, escalabilidad por copias, región nueva en caliente, país nuevo, adaptador de
  persistencia) MUST tener una variante ejecutable contra el despliegue en Kubernetes, sin
  eliminar la variante existente para Compose.
- **FR-019**: La saga de asignación de trabajo (caso exitoso y los tres casos de fallo con su
  compensación completa) MUST funcionar igual en el despliegue de Kubernetes que en Compose.
- **FR-020**: La trazabilidad de una petición por identificador de correlación MUST seguir
  funcionando entre procesos separados en Kubernetes; el procedimiento documentado MUST explicar
  cómo consultar los registros de varios procesos a la vez.
- **FR-021**: El despliegue con Docker Compose existente MUST seguir levantando el sistema
  completo exactamente igual que antes de esta historia; ningún cambio de esta historia MUST
  alterar su comportamiento.
- **FR-022**: La documentación del despliegue en Kubernetes MUST explicar el procedimiento
  completo (requisitos previos, creación del clúster, publicación de imágenes, despliegue,
  verificación y destrucción) con los comandos exactos a ejecutar.
- **FR-023**: La documentación MUST indicar el costo aproximado por hora y por día del clúster
  desplegado, y cómo dejar de pagar cuando no se está usando.
- **FR-024**: La documentación principal del proyecto MUST explicar que existen dos formas de
  desplegar el sistema y en qué situación conviene cada una.
- **FR-025**: Si el entorno de AWS de la cuenta usada no permite alguno de los recursos
  necesarios para el despliegue, la limitación encontrada y la alternativa adoptada MUST quedar
  documentadas explícitamente.
- **FR-026**: Los resultados de los escenarios de calidad ejecutados en Kubernetes MUST
  reportarse identificados como propios de ese entorno, sin mezclarse en la misma tabla que los
  resultados ya documentados para Compose.

### Key Entities

- **Clúster de Kubernetes**: el entorno de ejecución en AWS donde corren todos los componentes
  del sistema; tiene varios nodos y un componente de red que hace cumplir las reglas de
  conexión declaradas.
- **Manifiestos de despliegue**: la descripción declarativa de cada componente (servicios,
  bases de datos, clúster de mensajería, reglas de red, configuración) que el procedimiento usa
  para crear el estado deseado dentro del clúster.
- **Registro de contenedores**: el lugar donde se publican las imágenes de los seis servicios
  antes de que el clúster pueda desplegarlas, cada una etiquetada con la versión del código que
  contiene.
- **Reglas de red**: la declaración explícita de qué componente puede conectarse a cuál dentro
  del clúster; son las que sostienen el aislamiento entre servicios de dominio y sus bases de
  datos.
- **Secretos del clúster**: las credenciales (contraseñas de bases de datos, etc.) generadas en
  el momento del despliegue y almacenadas dentro del clúster, nunca en el repositorio.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona que no participó en la historia despliega el sistema completo en una
  cuenta de AWS limpia siguiendo únicamente la documentación, sin ayuda adicional, y lo logra.
- **SC-002**: El despliegue completo sobre un clúster ya existente toma un único comando y su
  destrucción también toma un único comando.
- **SC-003**: El 100% de los seis servicios, las cinco bases de datos y el clúster de
  mensajería quedan verificablemente sanos tras el despliegue.
- **SC-004**: La colección de Postman del BFF corre en verde (0 fallas) contra el sistema
  desplegado en Kubernetes.
- **SC-005**: Las nueve comprobaciones de aislamiento de red entre servicios, ya documentadas
  para Compose, se repiten en Kubernetes con el mismo resultado (conexión prohibida falla).
- **SC-006**: Los cinco escenarios de calidad de la entrega anterior se ejecutan en Kubernetes y
  producen resultados comparables a los de Compose, con cualquier diferencia explicada por
  escrito.
- **SC-007**: Tras eliminar el proceso de cada tipo de componente con estado (base de datos,
  almacén durable de Pulsar), el sistema recupera el 100% de los datos o mensajes previos y
  ninguna suscripción pierde su posición.
- **SC-008**: El despliegue con Docker Compose sigue levantando el sistema completo sin ninguna
  diferencia de comportamiento respecto a antes de esta historia.
- **SC-009**: El costo aproximado del entorno desplegado queda documentado en unidades de
  dinero por hora y por día, junto con el procedimiento para dejar de pagar.
- **SC-010**: Al destruir el despliegue con el comando único, la cuenta de AWS no retiene
  ningún recurso asociado que siga generando costo.

## Assumptions

- El procedimiento de esta historia se ejecuta sobre la misma cuenta de AWS educativa/del curso
  ya usada para el despliegue con Docker Compose existente; no se asume una cuenta empresarial
  con límites distintos.
- No se usan servicios gestionados equivalentes (bases de datos tipo RDS, Pulsar contratado);
  tanto las bases de datos como el clúster de mensajería se configuran y despliegan dentro del
  propio clúster de Kubernetes, igual que en Compose.
- El número de copias de cada componente se ajusta manualmente; no se implementa escalado
  automático por carga como parte de esta historia.
- No hay integración continua ni despliegue automático desde el repositorio; el despliegue se
  dispara siempre a mano siguiendo el procedimiento documentado.
- Existe un único entorno de Kubernetes (no ambientes separados de desarrollo/pruebas/
  producción), con la posibilidad de levantarlo en una configuración reducida o completa.
- No se implementan múltiples zonas de disponibilidad ni recuperación ante desastres como parte
  de esta historia.
- El guion que crea el tenant, los espacios de nombres, las políticas, los tópicos y las
  suscripciones del clúster de mensajería ya existe y es reutilizable tal cual; no se reescribe,
  solo se ejecuta en el momento adecuado del procedimiento de Kubernetes.
- El componente de red del clúster que hace cumplir las reglas de conexión declaradas
  (equivalente a un "network policy enforcer") está disponible y habilitado en el clúster
  usado; si la cuenta de AWS no lo permite, se documenta como limitación según FR-025.
