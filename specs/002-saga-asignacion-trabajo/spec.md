# Feature Specification: Saga de asignación de un trabajo, con reversiones y registro de estado

**Feature Branch**: `002-saga-asignacion-trabajo`

**Created**: 2026-09-20

**Status**: Draft

**Input**: User description: "docs/us-entrega-5/US-01-saga-asignacion-de-trabajo.md — implementar el patrón de sagas sobre gestión_trabajos, emparejamiento y acreditación (con compensación paso a paso) para que crear un trabajo termine en una asignación automática a un proveedor certificado y vigente, y añadir un servicio nuevo saga_log que solo observa los tres canales de eventos existentes y expone el estado y la línea de tiempo de cada transacción, sin agregar tópicos nuevos ni llamadas HTTP entre servicios."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Asignación automática de punta a punta (Priority: P1)

Como responsable de operaciones, cuando registro un trabajo con un proveedor
certificado disponible, quiero que el sistema lo asigne automáticamente sin
que nadie tenga que revisar candidatos a mano, verificando primero que el
proveedor elegido siga realmente habilitado en el momento de confirmar.

**Why this priority**: Es el camino feliz y la razón de ser de la historia:
hoy el trabajo se queda "creado" para siempre porque nadie lo asigna. Sin
esto no hay producto que demostrar.

**Independent Test**: Crear un trabajo válido con al menos un proveedor
certificado y vigente disponible; verificar que el trabajo termina en estado
asignado con el identificador del proveedor visible al consultarlo.

**Acceptance Scenarios**:

1. **Given** un proveedor certificado y vigente existe para la categoría y
   región del trabajo, **When** un cliente crea el trabajo, **Then** el
   trabajo termina en estado ASIGNADO con ese proveedor.
2. **Given** un trabajo fue asignado, **When** se revisan los registros de
   traza de los tres servicios, **Then** se ve la transacción recorrer
   Gestión de Trabajos → Emparejamiento → Acreditación → Gestión de
   Trabajos en orden, con el mismo identificador de correlación en cada
   paso.

---

### User Story 2 - Reversión limpia cuando algo falla (Priority: P1)

Como responsable de operaciones, cuando algo impide completar la asignación
(el proveedor ya no está vigente, no hay candidatos, o falla la asignación
final), quiero que el sistema deshaga automáticamente todo lo que ya había
hecho, para no quedar con proveedores bloqueados en trabajos que nunca se
concretaron ni con trabajos a medio asignar.

**Why this priority**: Es el riesgo concreto que motiva la historia: sin
reversión, un proveedor revocado podría quedar reservado indefinidamente, o
un trabajo quedar en un estado inconsistente. Tiene la misma criticidad que
el camino feliz porque ambos deben coexistir para que el sistema sea
confiable.

**Independent Test**: Provocar cada uno de los tres puntos de falla
(vigencia rechazada, sin candidatos, falla de asignación final) usando la
marca de simulación y verificar que en cada caso el trabajo termina
cancelado y ningún proveedor queda con una reserva colgada.

**Acceptance Scenarios**:

1. **Given** un proveedor fue propuesto y reservado, **When** Acreditación
   determina que ya no está vigente, **Then** la reserva se libera, el
   trabajo se cancela, y los tres pasos de reversión quedan registrados en
   orden inverso al de ida.
2. **Given** ningún proveedor certificado está disponible, **When** se crea
   el trabajo, **Then** el trabajo se cancela directamente, sin que se haya
   reservado a nadie.
3. **Given** la asignación final falla (por ejemplo, el trabajo fue
   cancelado externamente mientras la saga estaba en curso), **When** eso
   ocurre, **Then** el trabajo queda cancelado y el proveedor reservado
   queda liberado.
4. **Given** un proveedor quedó liberado por una compensación, **When** se
   crea un trabajo nuevo compatible, **Then** ese proveedor vuelve a
   aparecer como candidato.

---

### User Story 3 - Visibilidad de cada transacción sin leer cuatro bitácoras (Priority: P2)

Como integrante del equipo técnico, quiero poder consultar en qué punto va
o terminó cualquier transacción de asignación y por qué se revirtió, para
poder explicar y demostrar el comportamiento del sistema sin tener que
correlacionar manualmente los registros de varios servicios.

**Why this priority**: Es una necesidad real (hoy Acreditación no se puede
correlacionar con los otros dos servicios) pero el sistema funciona
correctamente sin ella; es una historia de observabilidad sobre un
comportamiento que las historias 1 y 2 ya garantizan.

**Independent Test**: Con el servicio de registro de sagas corriendo,
ejecutar una transacción completa y una compensada, y verificar que
consultando un solo endpoint por el identificador del trabajo se obtiene el
estado final y la línea de tiempo completa de pasos, sin necesidad de leer
las bitácoras de los demás servicios.

**Acceptance Scenarios**:

1. **Given** una transacción terminó exitosamente, **When** se consulta su
   estado por el identificador del trabajo, **Then** se obtiene estado
   COMPLETADA con sus cuatro pasos en orden cronológico.
2. **Given** una transacción se compensó, **When** se consulta su estado,
   **Then** se obtiene estado COMPENSADA con sus pasos de ida y de vuelta.
3. **Given** el servicio de registro de sagas estuvo caído durante una
   transacción, **When** se reactiva, **Then** recupera y registra todo lo
   que ocurrió mientras estuvo abajo, y las transacciones se completaron o
   compensaron con normalidad mientras tanto.
4. **Given** el broker entrega un mensaje duplicado, **When** el registro
   de sagas lo procesa, **Then** el paso no aparece duplicado en la línea
   de tiempo.

---

### Edge Cases

- ¿Qué pasa si dos trabajos compiten por el mismo proveedor casi al mismo
  tiempo y solo uno puede reservarlo? El segundo debe fallar limpio esa
  reserva y continuar con el siguiente candidato o compensar, sin dejar al
  proveedor reservado por ambos.
- ¿Qué pasa si un paso de reversión se pierde en tránsito? La transacción
  debe quedar visible como incompleta para que alguien la revise, en vez de
  perderse en silencio.
- ¿Qué pasa si una transacción nunca llega a un estado final (ni completada
  ni compensada) dentro de un tiempo razonable? Debe quedar marcada de forma
  distinguible de las transacciones en curso normales, para que alguien la
  investigue; el sistema no la revierte por sí solo.
- ¿Qué pasa si el servicio de registro de sagas recibe un tipo de mensaje
  que no le pertenece o que no puede asociar a ninguna transacción conocida?
  Debe ignorarlo sin afectar el procesamiento de los mensajes que sí
  reconoce.
- ¿Qué pasa si un consumidor existente (que no es parte de la saga) recibe
  un mensaje nuevo de tipo reversión por el mismo canal que ya escuchaba?
  Debe ignorarlo sin corromper su propio estado.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST, al crear un trabajo, iniciar automáticamente
  una búsqueda y reserva de un proveedor candidato, sin intervención manual.
- **FR-002**: El sistema MUST confirmar la vigencia del proveedor candidato
  contra la fuente de verdad de acreditaciones antes de comprometer la
  asignación del trabajo.
- **FR-003**: El sistema MUST asignar el trabajo al proveedor únicamente
  después de que su vigencia fue confirmada.
- **FR-004**: El sistema MUST revertir, paso a paso y en orden inverso al de
  ida, todo lo que ya se había hecho cuando cualquier paso de la
  transacción no puede completarse.
- **FR-005**: El sistema MUST liberar la reserva de un proveedor cuando la
  transacción que lo reservó se compensa, dejándolo disponible para
  trabajos futuros.
- **FR-006**: El sistema MUST cancelar un trabajo cuando su transacción de
  asignación se compensa por cualquier motivo.
- **FR-007**: El sistema MUST prevenir que dos transacciones concurrentes
  reserven simultáneamente al mismo proveedor para trabajos distintos.
- **FR-008**: El sistema MUST propagar, sin modificarlo, un mismo
  identificador de correlación a través de todos los mensajes que
  pertenecen a una misma transacción.
- **FR-009**: El sistema MUST permitir simular, mediante una marca opcional
  en la petición de creación del trabajo, que la transacción falle en un
  punto determinado (sin candidatos, vigencia rechazada, o falla en la
  asignación final), únicamente con fines de demostración y prueba.
- **FR-010**: El sistema MUST registrar, para cada paso de cada
  transacción, el servicio que lo produjo, el paso al que corresponde, si
  fue avance o reversión, y el momento exacto, de forma consultable.
- **FR-011**: El sistema MUST permitir consultar el estado y la línea de
  tiempo completa de una transacción específica usando el identificador del
  trabajo.
- **FR-012**: El sistema MUST permitir consultar todas las transacciones
  que se encuentran en un estado dado.
- **FR-013**: El sistema MUST permitir consultar, de un vistazo, cuántas
  transacciones hay en cada estado.
- **FR-014**: El sistema MUST clasificar cada transacción en uno de estos
  estados: en curso, completada, compensando, compensada, o incompleta (sin
  llegar a un estado final dentro de un tiempo razonable).
- **FR-015**: El componente de observación de sagas MUST NOT participar en
  ninguna decisión de negocio ni publicar ningún mensaje; su caída MUST NOT
  impedir que las transacciones se completen o se compensen con
  normalidad.
- **FR-016**: El sistema MUST procesar cada mensaje de forma idempotente,
  de modo que una entrega duplicada del mismo mensaje no duplique ni el
  efecto de negocio ni el registro de observación.
- **FR-017**: El sistema MUST comunicar todo lo que cruza entre servicios
  exclusivamente por mensajería; ningún servicio MUST llamar a otro
  directamente.
- **FR-018**: El sistema MUST mantener los mismos canales de comunicación
  que existían antes de esta funcionalidad; una reversión MUST viajar por
  el mismo canal que el paso que deshace, distinguida por su tipo.
- **FR-019**: El sistema MUST mantener el mismo criterio de ordenamiento por
  trabajo que ya existía (los mensajes de un mismo trabajo siguen
  procesándose en orden) al añadir esta funcionalidad.
- **FR-020**: Los consumidores que ya existían antes de esta funcionalidad
  MUST seguir funcionando sin cambios ni redespliegue.

### Key Entities

- **Transacción de asignación (saga)**: Representa el intento de asignar
  un trabajo a un proveedor de principio a fin. Atributos clave:
  identificador de correlación, trabajo asociado, estado (en curso,
  completada, compensando, compensada, incompleta), momento de inicio y de
  fin.
- **Paso de la transacción**: Un evento individual dentro de una
  transacción. Atributos clave: transacción a la que pertenece, servicio
  que lo produjo, número/nombre de paso, si es avance o reversión, momento
  exacto.
- **Trabajo**: La unidad de servicio que el cliente solicita. Atributos
  relevantes a esta historia: estado (creado, asignado, cancelado),
  proveedor asignado si aplica.
- **Reserva de proveedor**: La relación temporal entre un proveedor
  candidato y un trabajo mientras la transacción está en curso. Se libera
  al compensar o se confirma al completar.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los trabajos creados con un proveedor certificado
  y vigente disponible terminan asignados automáticamente, sin intervención
  manual.
- **SC-002**: El 100% de las transacciones que no pueden completarse (por
  cualquiera de los tres motivos de falla) terminan compensadas: cero
  proveedores quedan con una reserva colgada y cero trabajos quedan a medio
  asignar.
- **SC-003**: Cualquier persona del equipo técnico puede obtener el estado
  y la historia completa de una transacción consultando un único punto de
  información, sin leer los registros internos de ningún servicio.
- **SC-004**: La demostración completa de los cuatro escenarios (éxito y
  las tres formas de falla) se puede ejecutar con un solo comando y termina
  en menos de cinco minutos.
- **SC-005**: Detener el componente de observación de sagas no cambia el
  resultado de ninguna transacción en curso; al reactivarlo, el 100% de lo
  ocurrido durante la caída queda reflejado en las consultas.
- **SC-006**: Todo el comportamiento existente antes de esta funcionalidad
  (suscripciones actuales, pruebas automáticas, colección de pruebas de
  extremo a extremo) sigue funcionando sin cambios.

## Assumptions

- El proveedor certificado elegido como candidato es responsabilidad del
  mecanismo de selección ya existente; esta historia no cambia cómo se
  elige, solo agrega la confirmación de vigencia y la reserva antes de
  comprometer la asignación.
- La marca de simulación de fallos es exclusivamente una herramienta de
  demostración y prueba: no se documenta como funcionalidad del producto ni
  se protege con permisos, y puede quedar disponible en el ambiente de
  desarrollo/pruebas.
- No hay reintentos automáticos dentro de un paso: si un paso falla, la
  transacción se compensa; no se reintenta antes de compensar.
- No hay un tiempo límite que dispare compensación automática: una
  transacción que se queda a medias se marca como incompleta para que
  alguien la revise, pero el sistema no la revierte por sí solo.
- Revocar una acreditación y desasignar trabajos que ya tenía un proveedor
  (una saga distinta, sobre un proveedor ya confirmado) queda fuera de
  alcance de esta historia.
- El componente de observación de sagas no participa en ninguna decisión
  de negocio: es estrictamente un observador, no un orquestador.
- Cada transacción se identifica de forma consultable tanto por el
  identificador del trabajo (clave de negocio) como por el identificador de
  correlación (clave de traza técnica).
