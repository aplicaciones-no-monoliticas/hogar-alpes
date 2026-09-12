# Cómo se usó IA generativa en esta entrega

> La guía de la Entrega 4 dice que el tutor *«es consciente de que por medio de IA generativa se pueden generar soluciones plausibles y coherentes»* y que **todos** los integrantes deben poder sustentar, aclarar y defender el diseño. Este documento dice exactamente qué se delegó, qué no, y cómo se verificó cada cosa.

**Herramienta:** Claude Code (Anthropic), usado como par de programación por el equipo.

---

## 1. Qué se delegó y qué no

| Fase | Qué hizo la IA | Qué decidió el equipo |
|---|---|---|
| Escenarios de calidad | Nada | **Los fijó el tutor**: Modificabilidad (escenarios 1-3), Disponibilidad (6) y Escalabilidad (8). También aprobó extraer `operaciones` como servicio |
| Cuarto microservicio | Presentó dos candidatos —Acreditación y Gateway de Partners— con el argumento y el costo de cada uno | **El equipo eligió Acreditación** |
| Plataforma de despliegue | Presentó tres opciones con sus costos | **El equipo eligió** EC2 con Docker Compose, en AWS |
| Especificación, plan y tareas | Redacción, con criterios de aceptación verificables | **Aprobación explícita en cada fase** antes de escribir código |
| Implementación | Código, scripts de verificación y documentación | Revisión, ejecución y firma de cada bloque por su dueño |

Las decisiones de arquitectura que se sustentan —tipo de evento por flujo, formato y evolución de esquemas, topología de datos, CRUD frente a Event Sourcing— están argumentadas en `01-especificacion.md` y `02-plan-tecnico.md`, y cada una nombra su alternativa descartada y el costo aceptado. Ese es el material que el equipo defiende.

## 2. La regla que gobierna el trabajo: nada se da por terminado sin correr su verificación

Las 44 tareas de `03-tareas.md` tienen una columna **Criterio** —a qué criterio de aceptación y a qué ítem de la rúbrica responde— y una columna **Verificación** con un comando concreto. Una tarea solo se cierra cuando esa verificación se corrió y pasó.

No es una formalidad. Estos son los defectos que **aparecieron al verificar**, y que una revisión de lectura no habría encontrado:

| Hallazgo | Cómo apareció | Qué habría pasado sin verificar |
|---|---|---|
| `pulsar.schema` solo emite `"default"` si el campo se declara con `required_default=True`; sin eso el broker rechaza agregar un campo opcional | Spike INF-0 contra un broker real | La demostración de evolución de esquemas (CA-E1) habría fallado **en la sustentación**, pareciendo un problema de Pulsar |
| El archivo de entorno de Postman declaraba `trabajoId` vacío y eclipsaba la variable de la colección | Correr `newman` con el entorno, como lo haría el tutor | El tutor habría visto fallar el escenario 3 con `405` y `404` al importar el entorno |
| El consumidor de comandos moría ante un `TopicNotFound` y no volvía | Levantar el clúster con creación automática de tópicos deshabilitada | El servicio respondería `202` sin consumir nada, y nadie se enteraría |
| `initialize-cluster-metadata` fallaba por el plegado de YAML y por banderas retiradas en Pulsar 3.x | Levantar el clúster | Horas perdidas el fin de semana de la entrega |

Los cuatro están documentados con su evidencia en `decisiones.md`.

## 3. Rastro verificable

- **Commits**: los que se hicieron con asistencia llevan `Co-Authored-By: Claude`. El autor es el integrante que ejecutó y revisó el bloque.
- **Pull requests**: uno por bloque de tareas, desde la cuenta de quien lo hizo. La rúbrica exige contribuciones equitativas y visibles en commits y PR.
- **`decisiones.md`**: toda decisión tomada durante la implementación que no estaba en el plan, con la evidencia que la sostiene.
- **`resultados/`**: la salida de los scripts de escenario, que imprimen PASA/FALLA por criterio.

## 4. Qué debe poder defender cada integrante

Cada bloque tiene un dueño que lo ejecuta, lo verifica y lo sube. Además, la tarea `DOC-4` obliga a que **cada uno defienda en el ensayo una decisión que no implementó**: si Stiven solo puede explicar Operaciones, el equipo no está listo.

Preguntas que cualquiera del equipo debe poder responder sin ayuda:

- ¿Por qué `evt-trabajo` lleva eventos de integración y `evt-acreditacion` eventos de carga de estado?
- ¿Por qué la topología de datos es descentralizada y no híbrida, y qué se paga por eso?
- ¿Por qué Event Sourcing solo en Acreditación?
- ¿Por qué la ventana del escenario 6 la fijan el TTL y la cuota de backlog, y no la política llamada *retention*?
- ¿Por qué la suscripción de Emparejamiento es Failover y no Key_Shared?

## 5. Límites de lo que aquí se afirma

Este documento describe cómo se trabajó, no garantiza que el resultado sea correcto. Lo que respalda cada afirmación técnica es la verificación que acompaña a cada tarea y la evidencia guardada en `decisiones.md` y en `resultados/`. Donde algo no se pudo comprobar —por ejemplo, los 15.600 req/s del escenario 8, que no se reproducen en una sola máquina— está dicho de forma explícita en la especificación, junto con lo que sí se mide en su lugar.
