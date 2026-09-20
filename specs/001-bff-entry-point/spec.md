# Feature Specification: BFF — un solo punto de entrada y trazabilidad por petición

**Feature Branch**: `001-bff-entry-point`

**Created**: 2026-09-19

**Status**: Draft

**Input**: User description: "@US-02-bff.md" (`docs/us-entrega-5/US-02-bff.md`, Entrega 5, actividad (b): API tipo BFF + colección de Postman)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Una sola dirección para todas las funcionalidades (Priority: P1)

Una persona que usa o prueba el sistema (una aplicación cliente o alguien del equipo) hace todas sus peticiones contra **una sola dirección**, sin saber en qué puerto vive cada servicio ni cómo está dividido el sistema por dentro. Cada ruta que hoy exponen los cinco servicios de dominio (Trabajos, Seguimiento/Operaciones, Acreditaciones, Emparejamiento y Sagas) queda disponible bajo esa dirección con la misma ruta, el mismo cuerpo y el mismo código de respuesta.

**Why this priority**: es la base de todo lo demás. Sin el reenvío fiel no hay puerta de entrada, los endpoints compuestos no tienen sobre qué apoyarse y las demostraciones posteriores (incluida la saga de US-01) se escriben contra esta puerta. Es además la pieza de menor riesgo, pensada para terminarse primero.

**Independent Test**: Correr la colección de pruebas de la Entrega 4 apuntando a la dirección del BFF, cambiando únicamente las direcciones base del entorno (salvo la carpeta `0 · Salud del servicio`, ver FR-004). Si todas las aserciones pasan en verde, el reenvío es fiel.

**Acceptance Scenarios**:

1. **Given** el sistema levantado, **When** un cliente crea un trabajo con `POST /trabajos` contra el BFF, **Then** recibe el mismo código `202` y el mismo cuerpo que recibiría llamando directo al servicio de Trabajos, más el campo adicional `correlation_id` (FR-026).
2. **Given** un servicio de dominio que rechaza una petición por una regla de negocio (por ejemplo, una categoría no permitida en México), **When** la petición llega a través del BFF, **Then** el cliente recibe el mismo `400` con el mismo mensaje, sin reinterpretación.
3. **Given** un identificador que no existe, **When** el cliente consulta `GET /trabajos/{id}` a través del BFF, **Then** recibe el mismo `404` que devolvería el servicio.
4. **Given** una ruta que no existe en ningún servicio, **When** el cliente la solicita al BFF, **Then** recibe un `404` que incluye la lista de grupos de rutas disponibles.
5. **Given** un servicio de dominio detenido o que tarda demasiado, **When** el cliente llama a una ruta de ese servicio a través del BFF, **Then** recibe un `503` con un mensaje claro que nombra **cuál** servicio no está disponible, nunca un error interno ni una traza, y las rutas de los demás servicios siguen funcionando con normalidad.

---

### User Story 2 - Consultas compuestas en una sola llamada (Priority: P2)

Una persona que quiere saber «¿cómo va este trabajo?» obtiene la respuesta completa con **una sola llamada** en lugar de armar a mano, del lado del cliente, la respuesta a partir de cuatro servicios. El BFF ofrece cuatro rutas compuestas que no existen en ningún servicio: el detalle completo de un trabajo, el detalle completo de un proveedor, el estado general del sistema y la creación de un trabajo con la dirección donde seguir su saga.

**Why this priority**: es el valor visible del BFF frente a una simple redirección de rutas, y concreta la promesa de que la caída de un servicio no tumba al resto, ahora visible desde el borde. Depende de US1.

**Independent Test**: Con el sistema levantado, pedir `GET /trabajos/{id}/completo` para un trabajo con saga terminada y verificar que una sola respuesta trae el trabajo, su seguimiento, su emparejamiento y el estado de su saga; luego detener Operaciones y repetir la llamada.

**Acceptance Scenarios**:

1. **Given** un trabajo cuya cadena ya terminó de procesarse, **When** el cliente pide `GET /trabajos/{id}/completo`, **Then** recibe en una sola respuesta el trabajo, su seguimiento operativo, su emparejamiento y el estado de su saga.
2. **Given** el servicio de Operaciones detenido, **When** el cliente pide `GET /trabajos/{id}/completo`, **Then** recibe el trabajo, el emparejamiento y la saga, y la parte de seguimiento marcada como *no disponible* en lugar de una falla completa.
3. **Given** un trabajo recién creado que todavía no tiene seguimiento ni emparejamiento por consistencia eventual, **When** el cliente pide `GET /trabajos/{id}/completo`, **Then** esas partes se reportan como *«todavía no disponible»* (distinto de *no disponible* por caída) y la respuesta no es un `404`.
4. **Given** un proveedor con acreditación, **When** el cliente pide `GET /proveedores/{id}/completo` (con `{id}` = identificador de su acreditación), **Then** recibe su acreditación, su historial completo y si hoy aparece como candidato disponible.
5. **Given** el sistema en marcha, **When** el cliente pide `GET /estado-del-sistema`, **Then** recibe la salud de los seis componentes y el resumen de sagas por estado en una sola respuesta.
6. **Given** un cuerpo válido de trabajo, **When** el cliente hace `POST /trabajos/asignacion`, **Then** el trabajo se crea y la confirmación incluye la dirección donde seguir el avance de su saga.

---

### User Story 3 - Reconstruir una petición con una sola búsqueda (Priority: P2)

Una persona que diagnostica un problema toma el **código único de la petición** (identificador de correlación) y, con una sola búsqueda en los registros de los seis servicios, reconstruye en orden todo lo que pasó, en lugar de adivinar qué línea de cada servicio corresponde a qué petición. El código lo crea el BFF —una sola vez por petición, o lo respeta si el cliente lo manda— y lo devuelve siempre al cliente; todos los servicios lo copian en cada mensaje que publican y en cada línea de registro relacionada. Para seguir la vida completa de un trabajo a través de varias peticiones, los registros llevan además el `trabajo_id`.

**Why this priority**: es la mejora de diagnóstico más importante de la entrega, pero atraviesa los cinco servicios existentes y por eso se verifica sobre una saga real, después de tener la puerta de entrada (US1). Cubre incluso flujos sin trabajo, como acreditar un proveedor.

**Independent Test**: Disparar una saga real a través del BFF, tomar el identificador que devuelve la respuesta, buscarlo en los registros de los seis servicios y comprobar que aparecen todos los pasos de la cadena, en orden.

**Acceptance Scenarios**:

1. **Given** una petición sin identificador de correlación, **When** entra al BFF, **Then** el BFF crea uno único y lo devuelve en la cabecera `X-Correlation-Id` de la respuesta.
2. **Given** una petición que ya trae `X-Correlation-Id`, **When** entra al BFF, **Then** el BFF respeta ese valor, lo propaga hacia adentro y lo devuelve igual.
3. **Given** cualquier tipo de respuesta —exitosa, error de negocio (`400`, `404`, `409`) o servicio no disponible (`503`)—, **When** el BFF responde, **Then** la respuesta lleva la cabecera `X-Correlation-Id`.
4. **Given** una petición que inicia una saga (`POST /trabajos` o `POST /trabajos/asignacion`), **When** el BFF responde, **Then** el identificador viaja también en el cuerpo, junto al identificador del trabajo.
5. **Given** una saga real disparada a través del BFF, **When** se busca el identificador devuelto en los registros de los seis servicios, **Then** una sola búsqueda muestra la cadena completa, en orden, y el mismo valor aparece en los mensajes publicados (en el sobre y en las propiedades).
6. **Given** una petición directa a la API de un servicio, o un mensaje publicado por una herramienta externa sin identificador válido (vacío o con caracteres no permitidos), **When** el servicio lo recibe, **Then** crea el identificador y lo propaga desde ahí, de modo que ninguna cadena queda sin identificar.
7. **Given** los mensajes de un mismo trabajo en el tópico de eventos de trabajo, **When** se publican con el nuevo identificador de correlación, **Then** siguen cayendo todos en la misma partición y el orden dentro de un trabajo no cambia.
8. **Given** un trabajo con dos peticiones (su creación y un cambio de estado), **When** se busca su `trabajo_id` en los registros, **Then** aparecen las líneas de ambas peticiones con dos identificadores de correlación distintos, y buscar cada identificador de correlación por separado trae solo las líneas de su petición.

---

### User Story 4 - Colección de pruebas para el BFF (Priority: P3)

Una persona del equipo dispone de una colección de Postman nueva y de dos entornos (local y AWS) para probar el BFF, organizada por temas (salud, trabajos, acreditaciones, emparejamiento, seguimiento, sagas, endpoints compuestos, saga de punta a punta, errores y degradación, trazabilidad), con aserciones automáticas en cada petición, ejecutable sin intervención manual.

**Why this priority**: es el entregable de demostración de la actividad (b) y la evidencia de que los criterios anteriores se cumplen, pero no aporta comportamiento nuevo al sistema.

**Independent Test**: Levantar el sistema desde cero y ejecutar la colección completa con `newman`; debe terminar en verde sin intervención manual.

**Acceptance Scenarios**:

1. **Given** un sistema recién levantado, **When** se ejecuta la colección completa contra el entorno local, **Then** todas las peticiones y aserciones pasan en verde.
2. **Given** la carpeta «Saga de punta a punta», **When** se ejecuta, **Then** demuestra desde el BFF el caso exitoso y los tres casos de fallo de US-01, verificando el estado final de la saga en cada uno.
3. **Given** la carpeta «Trazabilidad», **When** se ejecuta, **Then** verifica que el BFF crea el identificador cuando no viene, respeta el que el cliente manda y lo devuelve en la cabecera de toda respuesta, incluidas las de error y las de servicio caído.
4. **Given** los entornos `bff-local` y `bff-aws`, **When** se cambia de uno a otro, **Then** la colección funciona sin modificar peticiones.

---

### User Story 5 - Agregar el BFF sin romper el aislamiento entre servicios (Priority: P1)

Quien mantiene la arquitectura necesita la garantía de que agregar el BFF **no** crea ninguna vía de comunicación **síncrona** entre servicios de dominio: siguen comunicándose entre sí únicamente por eventos de Pulsar, y las únicas llamadas HTTP son las del BFF hacia adentro, nunca al revés. Que varios servicios compartan una red Docker no cuenta como comunicación; lo que se prohíbe es que uno llame a otro. El BFF es un componente de borde, no un servicio de dominio.

**Why this priority**: la regla «ningún servicio llama a otro por HTTP» es una promesa central del proyecto; si el BFF la rompe, invalida el resto del diseño. Se verifica, no se supone.

**Independent Test**: Revisar que ningún servicio de dominio tiene un cliente HTTP ni una variable de entorno que apunte a otro servicio de dominio o al BFF; que el único componente con llamadas HTTP hacia servicios es el BFF; y que el BFF no tiene conexión al broker ni a las bases de datos.

**Acceptance Scenarios**:

1. **Given** el sistema levantado con el BFF, **When** se revisa el código y la configuración de los servicios de dominio, **Then** ninguno llama por HTTP a otro servicio de dominio ni al BFF, ninguno adquirió un cliente HTTP ni una variable de entorno que apunte a otro servicio de dominio o al BFF, y toda comunicación entre ellos sigue siendo por eventos de Pulsar; el BFF solo atiende peticiones de clientes (nunca las origina un servicio de dominio).
2. **Given** el BFF levantado, **When** se revisa su configuración y dependencias, **Then** no declara ningún almacenamiento de datos, ninguna conexión a base de datos y ninguna dependencia del broker de mensajes.

---

### Edge Cases

- **Identificador de correlación inválido del cliente**: si la cabecera `X-Correlation-Id` viene vacía, excesivamente larga o con caracteres que podrían alterar las líneas de registro, se trata como ausente: el BFF crea uno nuevo y lo devuelve.
- **Servicio de atrás lento (no caído)**: si un servicio excede su tiempo límite, se comporta como caído: `503` que nombra el servicio (en rutas reenviadas) o parte *no disponible* (en endpoints compuestos), sin dejar la petición colgada.
- **Todas las partes de un endpoint compuesto caídas**: si ninguna de las partes puede obtenerse por falla de servicio, el BFF responde `503` explicando cuáles servicios no responden, en lugar de una respuesta compuesta vacía (salvo `/estado-del-sistema`, FR-015).
- **Identificador de trabajo inexistente en un endpoint compuesto**: si el servicio de Trabajos indica que el trabajo no existe, el BFF devuelve ese `404` tal cual; no lo disfraza de «todavía no disponible».
- **Registro de sagas aún no construido**: si el registro de sagas de US-01 todavía no existe cuando el BFF esté listo, sus tres rutas y la parte de saga de los endpoints compuestos se incorporan en una segunda pasada; mientras tanto esa parte se reporta como no disponible y el resto funciona.
- **Consistencia eventual**: un trabajo recién creado sin seguimiento ni emparejamiento no es un error; se reporta como *«todavía no disponible»*.
- **Mensaje entrante sin identificador**: un servicio que recibe un mensaje sin identificador de correlación crea uno y lo propaga; nunca publica un mensaje sin identificar.
- **Varias copias del BFF**: al levantar dos o más copias del BFF sin coordinación entre ellas, todas se comportan igual; ninguna depende de estado compartido.
- **Petición que no pasa por el BFF**: sigue siendo válida y queda identificada por quien la recibe.
- **Error interno inesperado del BFF**: nunca se expone una traza ni un `500` sin explicación; el cliente recibe un mensaje comprensible y el identificador de correlación.

## Requirements *(mandatory)*

### Functional Requirements

**Puerta de entrada y reenvío**

- **FR-001**: El sistema DEBE ofrecer un componente de entrada único (BFF) que responda en una sola dirección y se levante junto con el resto del sistema, sin configuración manual adicional.
- **FR-002**: El BFF DEBE exponer, con la misma ruta, el mismo cuerpo y el mismo código de respuesta, todas las rutas de los servicios de dominio:
  - Trabajos: `POST /trabajos`, `GET /trabajos/{id}`, `GET /trabajos?estado=`, `PUT /trabajos/{id}/estado`.
  - Seguimiento: `GET /seguimientos/{id}`, `GET /seguimientos/conteo`, `GET /eventos-procesados/conteo`.
  - Acreditaciones: `POST /acreditaciones`, `PUT /acreditaciones/{id}/aprobar`, `PUT /acreditaciones/{id}/revocar`, `GET /acreditaciones/{id}`, `GET /acreditaciones/{id}/eventos`.
  - Emparejamiento: `GET /candidatos`, `GET /emparejamientos/{id}`.
  - Sagas: `GET /sagas/{id}`, `GET /sagas?estado=`, `GET /sagas/resumen`.
- **FR-003**: Cuando el servicio de atrás responde con normalidad o con un error de negocio (`400`, `404`, `409`), el BFF DEBE devolver esa respuesta sin modificar código ni cuerpo. El BFF NO DEBE agregar, validar ni reinterpretar reglas de negocio ni transformar datos de dominio. Única excepción: en `POST /trabajos` con respuesta `2xx` el BFF **agrega** el campo `correlation_id` al objeto JSON (FR-026), sin modificar ni quitar ningún campo del servicio. Las respuestas de error se devuelven byte a byte.
- **FR-004**: La colección de pruebas de la Entrega 4 DEBE pasar en verde contra el BFF cambiando únicamente las direcciones base del entorno (`baseUrl`, `baseUrlOps`), excepto la carpeta `0 · Salud del servicio`, que verifica el `/health` de un servicio concreto y no es una ruta reenviada (el BFF tiene su propio `/health`).
- **FR-005**: Cuando una ruta no existe en ningún servicio, el BFF DEBE responder `404` con la lista de grupos de rutas disponibles.
- **FR-006**: Las direcciones de los servicios de atrás DEBEN ser configurables, con valores por defecto que funcionen en el entorno de contenedores local, de modo que pasar de local a AWS o a Kubernetes no exija cambiar código.
- **FR-007**: El BFF NO DEBE guardar estado de ningún tipo, de modo que puedan levantarse varias copias sin coordinación.
- **FR-008**: El BFF NO DEBE tener base de datos ni conexión al broker de mensajes: no publica ni consume mensajes.
- **FR-009**: El BFF DEBE construirse con el mismo stack tecnológico y las mismas versiones que ya usan los demás servicios, sin incorporar ningún marco o tecnología nueva al proyecto (se excluye explícitamente cualquier esquema de consulta nuevo, como GraphQL).

**Manejo de fallos**

- **FR-010**: Cuando un servicio de atrás no responde o excede su tiempo límite, el BFF DEBE responder `503` con un mensaje claro que nombre el servicio no disponible y con el identificador de correlación en la cabecera.
- **FR-011**: Cuando un servicio de atrás está caído, las rutas de los demás servicios DEBEN seguir funcionando con normalidad.
- **FR-012**: El BFF NUNCA DEBE devolver una traza de error ni un `500` sin explicación.
- **FR-012b**: Cuando un servicio de atrás responde con un `5xx`, el BFF DEBE responder `502` con el nombre del servicio (`servicio`) y el código recibido (`status_upstream`), sin reenviar el cuerpo del servicio. Toda respuesta con código menor a `500` del servicio (incluidos `4xx` distintos de `400`, `404` y `409`) se devuelve sin modificar.

**Endpoints compuestos**

- **FR-013**: `GET /trabajos/{id}/completo` DEBE devolver, en una sola respuesta, el trabajo, su seguimiento operativo, su emparejamiento y el estado de su saga.
- **FR-014**: `GET /proveedores/{id}/completo` DEBE devolver, en una sola respuesta, la acreditación del proveedor, su historial completo y si hoy aparece como candidato disponible. `{id}` es el identificador de la **acreditación** (no el `proveedor_id`), porque es el que expone `GET /acreditaciones/{id}`; la respuesta incluye el `proveedor_id`.
- **FR-015**: `GET /estado-del-sistema` DEBE devolver, en una sola respuesta, la salud de los seis componentes y el resumen de sagas por estado. Responde siempre `200`, incluso con todos los servicios de atrás caídos, porque el propio BFF es un componente disponible (excepción a la regla del `503` de los demás compuestos).
- **FR-016**: `POST /trabajos/asignacion` DEBE crear el trabajo y devolver, junto con la confirmación, la dirección donde seguir el avance de su saga.
- **FR-017**: Los endpoints compuestos DEBEN degradar parcialmente: si un servicio de atrás no responde, DEBEN devolver lo que sí pudieron obtener y marcar la parte faltante como *no disponible*, en lugar de fallar completos.
- **FR-018**: Los endpoints compuestos DEBEN distinguir entre una parte *no disponible* (el servicio no responde) y una parte *todavía no disponible* (aún no existe por consistencia eventual), y NO DEBEN devolver `404` por esta última.
- **FR-019**: Las consultas internas de un endpoint compuesto DEBEN hacerse en paralelo, cada una con su propio tiempo límite.
- **FR-020**: Los endpoints compuestos DEBEN responder en menos de dos segundos (p95) en condiciones normales: sistema recién levantado, 50 peticiones con concurrencia 5 y ningún servicio de atrás caído ni lento. Con un servicio lento, `GET /proveedores/{id}/completo` (dos fases) puede tardar hasta el doble del tiempo límite por llamada; eso queda fuera de las condiciones normales.

**Aislamiento entre servicios**

- **FR-021**: Agregar el BFF NO DEBE crear ninguna vía de comunicación **síncrona** entre servicios de dominio: estos siguen comunicándose entre sí únicamente por eventos de Pulsar. El BFF es el único componente que hace llamadas HTTP hacia los servicios, y lo hace siempre desde el BFF hacia adentro; ningún servicio de dominio lo llama ni llama a otro. Compartir una red Docker no es comunicación; la cláusula de redes del Principio I se trata como excepción documentada (plan, Complexity Tracking, y `docs/decisiones.md`). Como defensa adicional, cada red exclusiva del BFF DEBE contener únicamente al BFF y a **un solo** servicio de dominio, y el BFF NO DEBE compartir red con el broker ni con las bases de datos. La verificación es sobre el código y la configuración (ver FR-022), no sobre la resolución de nombres.
- **FR-022**: Ningún servicio de dominio DEBE adquirir un cliente HTTP ni una variable de entorno que apunte a otro servicio de dominio o al BFF. El tráfico DEBE ir solo del BFF hacia adentro.

**Identificador de correlación**

- **FR-023**: El BFF DEBE crear un identificador de correlación único por petición cuando esta no lo trae, y DEBE respetar el valor recibido en la cabecera `X-Correlation-Id` cuando el cliente lo manda (salvo los valores inválidos descritos en Edge Cases).
- **FR-024**: El BFF DEBE enviar el identificador hacia adentro en la cabecera `X-Correlation-Id`.
- **FR-025**: El BFF DEBE devolver el identificador en la cabecera `X-Correlation-Id` de **todas** sus respuestas, sin excepción: correctas, de error de negocio (`400`, `404`, `409`) y de servicio no disponible (`503`).
- **FR-026**: Las peticiones que inician una saga (`POST /trabajos` y `POST /trabajos/asignacion`) DEBEN devolver además el identificador en el cuerpo de la respuesta, junto al identificador del trabajo.
- **FR-027**: Cada servicio DEBE colocar el identificador recibido en **cada mensaje que publica**, tanto en el sobre del mensaje como en sus propiedades, y DEBE leerlo del mensaje que consume para volver a propagarlo, sin importar cuántos saltos dé la cadena.
- **FR-028**: Cada servicio DEBE escribir el identificador en **todas** las líneas de registro relacionadas con esa petición, de modo que una sola búsqueda reconstruya la cadena completa en orden, incluso en flujos sin trabajo (por ejemplo, acreditar un proveedor).
- **FR-028b**: Además del identificador de correlación, cada línea de registro que un servicio (o el BFF) escribe mientras atiende algo de un trabajo —una petición cuya ruta lleva el identificador del trabajo o un mensaje que trae `trabajo_id`— DEBE llevar también `trabajo_id=<id>`, de modo que una sola búsqueda por `trabajo_id` reconstruya la vida completa de un trabajo a través de varias peticiones, cada una con su propio identificador de correlación. El valor se escribe solo si cumple el mismo formato que el identificador de correlación; las líneas emitidas antes de que el servicio conozca el identificador del trabajo no lo llevan.
- **FR-029**: Si una petición o un mensaje llega a un servicio sin identificador de correlación (directo a su API o publicado por una herramienta externa sin identificador válido), quien lo recibe DEBE crear uno y propagarlo desde ahí.
- **FR-030**: El identificador de correlación NO DEBE aparecer en ninguna entidad de dominio ni en ninguna tabla de negocio; DEBE viajar solo por el borde de cada servicio (de la petición o mensaje entrante al mensaje saliente).
- **FR-031**: La clave de partición del tópico de eventos de trabajo DEBE seguir siendo el identificador del trabajo, sin cambios en el orden dentro de un trabajo, el número de particiones ni el tipo de suscripción. No DEBE cambiar el contrato de los mensajes: cambia el valor escrito en un campo que ya existe, no la forma del mensaje.

**Colección de pruebas**

- **FR-032**: DEBE existir la colección `postman/hogar-alpes-bff.postman_collection.json` con las diez carpetas descritas en la historia (`0 · Salud` a `9 · Trazabilidad`) y al menos una aserción automática por petición.
- **FR-033**: DEBEN existir los entornos `bff-local` y `bff-aws`.
- **FR-034**: La colección completa DEBE correr en verde con `newman`, sin intervención manual, contra un sistema recién levantado.
- **FR-035**: La carpeta «Saga de punta a punta» DEBE demostrar desde el BFF el caso exitoso y los tres casos de fallo de US-01, verificando el estado final de la saga en cada uno.

**Pruebas y documentación**

- **FR-036**: El BFF DEBE incluir pruebas automáticas del reenvío, de la composición y del comportamiento ante un servicio caído, que no requieran los servicios reales.
- **FR-037**: El `README.md` del proyecto DEBE explicar qué es el BFF, por qué existe, y que sigue siendo válido llamar directo a cada servicio (el BFF es una puerta adicional, no obligatoria).
- **FR-038**: El `README.md` del servicio BFF DEBE listar todas las rutas, a qué servicio va cada una, qué devuelve cada endpoint compuesto y cómo seguir una petición por los registros con el identificador de correlación.
- **FR-039**: La decisión de diseño (el BFF como componente de borde frente a la regla de no llamadas HTTP entre servicios) DEBE anotarse en `docs/decisiones.md`, y `docs/actividades.md` DEBE registrar quién lo hizo con enlaces a sus *commits* y *pull request*.

### Key Entities *(include if feature involves data)*

- **Petición entrante**: solicitud de un cliente al BFF. Tiene una ruta, un cuerpo opcional y un identificador de correlación (recibido o creado). No se persiste.
- **Identificador de correlación**: código único que identifica una petición a lo largo de toda su cadena. Se crea una sola vez (en el BFF o, si la petición no pasa por él, en quien la recibe), se devuelve al cliente y se copia tal cual en mensajes y registros. Es información de transporte, no un dato de negocio, y es independiente de la clave de partición. El `trabajo_id` lo complementa en los registros: la correlación sigue **una petición**; el `trabajo_id` sigue **la vida de un trabajo**.
- **Servicio de dominio destino**: uno de los cinco servicios de atrás (Trabajos, Operaciones/Seguimiento, Acreditación, Emparejamiento, Sagas). Cada grupo de rutas se asocia a exactamente uno.
- **Respuesta compuesta**: respuesta del BFF que junta partes provenientes de varios servicios. Cada parte tiene un estado: disponible, *todavía no disponible* (consistencia eventual) o *no disponible* (servicio sin respuesta).
- **Estado de componente**: salud reportada por cada uno de los seis componentes del sistema, agregada en `GET /estado-del-sistema` junto al resumen de sagas por estado.
- **Saga**: transacción distribuida de asignación de trabajo (US-01). Este alcance solo la consulta y expone; su lógica no forma parte de esta especificación.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las rutas de los cinco grupos de servicios está disponible desde una sola dirección con idéntico código y cuerpo de respuesta (salvo el campo adicional `correlation_id` de FR-026), comprobado porque la colección de la Entrega 4 pasa en verde cambiando solo las direcciones base (salvo la carpeta `0 · Salud del servicio`, ver FR-004).
- **SC-002**: Responder «¿cómo va este trabajo?» requiere 1 petición en lugar de 4 y devuelve el trabajo, su seguimiento, su emparejamiento y el estado de su saga.
- **SC-003**: Los endpoints compuestos responden en menos de 2 segundos (p95) en condiciones normales (definidas en FR-020).
- **SC-004**: Con cualquier servicio de dominio detenido, el 100 % de las peticiones a los demás servicios sigue respondiendo con normalidad, el 100 % de las peticiones al servicio detenido recibe un aviso que lo nombra, y 0 respuestas exponen una traza o un error sin explicación.
- **SC-005**: Con un servicio detenido, los endpoints compuestos entregan el 100 % de las partes que sí están disponibles y marcan explícitamente las que no.
- **SC-006**: El 100 % de las respuestas del BFF —exitosas, de error de negocio y de servicio no disponible— lleva el identificador de correlación en su cabecera.
- **SC-007**: Con una sola búsqueda del identificador devuelto por el BFF en los registros de los seis servicios se reconstruye la cadena completa de una saga real, con 0 eslabones faltantes y en orden.
- **SC-008**: El 100 % de los mensajes publicados por los servicios en una saga real lleva el identificador de correlación recibido, tanto en el sobre como en las propiedades.
- **SC-009**: El orden dentro de un mismo trabajo no cambia: el 100 % de los mensajes de un trabajo cae en la misma partición y el escenario de escalabilidad existente pasa sin modificaciones.
- **SC-010**: 0 vías de comunicación síncrona entre servicios de dominio tras agregar el BFF (toda comunicación entre ellos sigue siendo por eventos); 0 clientes HTTP o variables de entorno hacia otro servicio de dominio o hacia el BFF; 0 entidades de dominio o tablas de negocio con el identificador de correlación.
- **SC-011**: Una petición que no pasa por el BFF queda identificada en el 100 % de los casos, sea directa a la API de un servicio o publicada por una herramienta externa sin identificador válido.
- **SC-012**: Desde un clon limpio, todo el sistema (incluido el BFF) se levanta con un solo comando, y la colección de Postman del BFF y la de los servicios corren en verde con `newman` sin intervención manual.
- **SC-013**: Con una sola búsqueda del `trabajo_id` en los registros se reconstruye la vida de un trabajo a través de al menos dos peticiones (creación y cambio de estado), con dos identificadores de correlación distintos; buscar cada identificador de correlación devuelve solo las líneas de su petición.

## Assumptions

- **«No alcanzarse entre sí» significa comunicación síncrona, no red.** Cuando la historia (CA-2.12, R5-7) dice que los servicios de dominio «siguen sin alcanzarse entre sí», se refiere a que no se llaman por HTTP y se comunican solo por eventos de Pulsar. No exige aislamiento de red: hoy las API y los consumidores comparten `red-broker` y se resuelven por nombre (comprobado con Docker el 2026-09-19), y eso es aceptable porque compartir red no es comunicar. La topología de la Entrega 4 **no se modifica**. En consecuencia, la comprobación de CA-2.12 **no** es «el nombre de otro servicio no resuelve» (esa prueba solo aplica a las bases de datos, donde el aislamiento sí es de red) sino la revisión del código y la configuración descrita en FR-021/FR-022. Un texto de `docs/hoja-verificacion-infraestructura.md` (§6) presenta el aislamiento entre APIs como un hecho de red; debe corregirse para decir que lo garantiza el código y el uso exclusivo de Pulsar. La excepción sobre redes (las redes `red-bff-<svc>` hacen que cada API de dominio comparta red con el BFF) se documenta en `docs/decisiones.md`; no exime a los servicios de dominio entre sí.
- **Los «seis componentes»** son los cinco servicios de dominio (Trabajos, Operaciones, Acreditación, Emparejamiento y el registro de Sagas de US-01) más el propio BFF. La frase «el BFF alcanza a los seis» de la historia se entiende como «alcanza a los cinco servicios de dominio»; «seis servicios» en los registros incluye al BFF, que también escribe el identificador en sus registros.
- **El BFF es un componente de borde, no un servicio de dominio**. Su excepción a la regla «ningún servicio llama a otro por HTTP» aplica solo al BFF y debe quedar justificada por escrito en `docs/decisiones.md`. Los cinco servicios de dominio siguen sin comunicarse entre sí por HTTP.
- **Orden de construcción**: esta historia se termina antes que la saga (US-01). Si el registro de sagas aún no existe, sus tres rutas y la parte de saga del endpoint compuesto llegan en una segunda pasada; solo hay que acordar desde el inicio los nombres de esos tres endpoints.
- **Alcance de la propagación**: el cambio del identificador de correlación afecta a los servicios existentes (para copiarlo en mensajes y registros) y no solo al BFF. Por diseño no cambia ningún contrato de mensaje, porque el campo del sobre ya existe con su valor por defecto. El generador de carga actual publica `correlation_id = trabajo_id` (un valor válido, que se respeta); el caso «sin identificador» se ejercita publicando un mensaje con el campo vacío.
- **Cuerpo de `POST /trabajos/asignacion`**: acepta el mismo cuerpo de entrada que `POST /trabajos` y devuelve además la dirección de seguimiento de la saga.
- **Tiempos límite por llamada**: cada llamada interna tiene su propio tiempo límite, definido durante la planificación, de modo que un servicio lento no deje colgada una petición ni un endpoint compuesto.
- **Identificador inválido del cliente**: se considera inválido si está vacío, es excesivamente largo o contiene caracteres que podrían alterar los registros; se sustituye por uno nuevo. Los límites exactos se fijan en la planificación.
- **Endpoint compuesto sin ninguna parte disponible**: se responde `503` (no una respuesta compuesta vacía); con al menos una parte disponible, se responde con la degradación parcial. Excepción: `/estado-del-sistema` siempre responde `200` (FR-015).
- **Fuera de alcance**: autenticación y autorización (incluido el *Gateway de Partners*), límites de tasa y control de consumo por cliente, caché, interfaz gráfica, GraphQL o cualquier esquema nuevo de consulta, y el retiro o cierre de las APIs de los servicios (siguen expuestas y siguen siendo la forma de medir los escenarios de calidad).
- **El BFF es un punto único de falla aceptado**: se mitiga porque no tiene estado (se pueden levantar varias copias) y porque las APIs de los servicios siguen abiertas como camino alterno.
- **Dependencias**: la colección de pruebas de la Entrega 4, el generador de carga, el escenario de escalabilidad y la comprobación de aislamiento de bases de datos ya existen y se reutilizan; el registro de sagas de US-01 es una dependencia para las rutas de sagas y la parte de saga de los endpoints compuestos.
- **Restricciones del proyecto que se respetan**: los servicios de dominio nuevos nacen de la plantilla de servicios existente (el BFF, que no es de dominio, parte solo de su esqueleto: plan, Complexity Tracking); el sistema completo se levanta desde un clon limpio con un solo comando y variables con valor por defecto; cada servicio expone su verificación de salud.
