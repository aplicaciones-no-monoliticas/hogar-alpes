<!--
SYNC IMPACT REPORT (temporal; eliminar antes de commitear)
- Version change: (plantilla sin rellenar, sin version) -> 1.0.0
- Principios modificados: ninguno renombrado; los 5 espacios de la plantilla se rellenaron y se
  agrego un sexto principio (VI. Verificacion Honesta)
    I.   Comunicacion Solo por Eventos
    II.  Contratos con Esquema y Evolucion Compatible
    III. Capas Separadas y Servicios Autonomos
    IV.  Comportamiento Cambiable por Datos, No por Codigo
    V.   Resiliencia por Diseno: Al-Menos-Una-Vez e Idempotencia
    VI.  Verificacion Honesta (NON-NEGOTIABLE)
- Secciones agregadas: Restricciones Tecnicas y de Despliegue; Flujo de Desarrollo y Puertas de Calidad
- Secciones eliminadas: ninguna
- Plantillas dependientes: no se modifican aqui; leen la constitucion en tiempo de ejecucion
- TODOs diferidos: ninguno
- Fuentes: README.md, docs/decisiones.md, docs/01-especificacion.md (RS-1..RS-6)
-->
# Hogar de los Alpes Constitution

## Core Principles

### I. Comunicacion Solo por Eventos
Los servicios `gestion_trabajos`, `operaciones`, `acreditacion` y `emparejamiento` MUST
comunicarse exclusivamente por mensajes sobre Apache Pulsar.

- Ningun servicio MUST llamar a otro por HTTP; no hay clientes HTTP hacia otros servicios en el
  codigo ni variables de entorno que apunten a otro servicio.
- Cada servicio MUST tener su propia base de datos y MUST NOT leer la de otro. En Compose, cada
  servicio comparte red unicamente con el broker y con su propia base.
- Quien publica un evento MUST NOT esperar respuesta de sus consumidores: avisa y sigue.
- Todo lo que un servicio necesite de otro MUST llegar como proyeccion local alimentada por
  eventos, no como consulta sincrona.

**Rationale**: la disponibilidad (un servicio caido 30 minutos no produce errores en el resto) y
el aislamiento solo se sostienen si no existe ninguna ruta sincrona entre servicios.

### II. Contratos con Esquema y Evolucion Compatible
Todo mensaje entre servicios MUST tener un esquema declarado en `contratos/` y registrado en el
broker (RS-1). La compatibilidad MUST fijarse explicitamente en `FULL_TRANSITIVE`, nunca la que
venga por defecto (RS-3).

- Todo campo MUST declararse `Tipo(default=None, required_default=True)`; sin default el broker
  rechaza cualquier evolucion.
- Los campos nuevos MUST agregarse al final. `_sorted_fields` MUST NOT usarse.
- Los valores de dominio abiertos (estado, categoria, pais) MUST viajar como texto; las
  enumeraciones Avro cerradas estan prohibidas (RS-5).
- Cada contrato MUST repetir de forma explicita los ocho campos del sobre CloudEvents (`id`,
  `type`, `time`, `ingestion`, `specversion`, `datacontenttype`, `service_name`,
  `correlation_id`); la herencia de `Record` los pierde en silencio.
- Un cambio de tipo, renombre o de significado MUST crear un stream nuevo `-v2` con publicacion
  dual durante la migracion (RS-4). La version MUST ser visible en el codigo (`schema/v1`,
  `schema/v2`).
- `herramientas/verificar_contratos.py` MUST pasar antes de fusionar cualquier cambio a
  `contratos/`.

**Rationale**: el broker rechaza los cambios incompatibles; esa garantia no debe depender de que el
equipo se acuerde de revisarlos.

### III. Capas Separadas y Servicios Autonomos
Dentro de `servicios/<nombre>/`, dominio, aplicacion (casos de uso) e infraestructura (base de
datos, Pulsar) MUST vivir en carpetas distintas, con dependencias apuntando hacia el dominio.

- El dominio MUST NOT importar de infraestructura. Cambiar el mecanismo de persistencia MUST
  implicar 0 archivos de reglas de negocio cambiados (escenario MOD-1).
- El seedwork MUST duplicarse por servicio (decision TO-7): no hay libreria compartida en tiempo
  de compilacion entre servicios. Los servicios nuevos MUST nacer copiando `servicios/_plantilla/`.
- El seedwork MUST usar imports relativos y MUST NOT nombrar ningun dominio ajeno.
- Un defecto corregido en una copia del seedwork MUST corregirse en todas las copias (plantilla y
  los cuatro servicios) dentro del mismo cambio o con una tarea registrada.
- Los procesos de API y consumidor de un servicio MUST ser procesos distintos de la misma imagen.
  El consumidor MUST NOT ser un hilo dentro de la aplicacion web.

**Rationale**: la duplicacion es deliberada y visible; preferimos repeticion explicita a un
acoplamiento que falla en silencio, y aceptamos el costo de sincronizar las copias.

### IV. Comportamiento Cambiable por Datos, No por Codigo
Lo que varia por pais, region o ciclo de vida MUST estar en configuracion o datos, no en codigo.

- Las reglas regionales (categorias y urgencias permitidas por pais) MUST vivir en
  `infra/sidecar/reglas_regionales.json`, montado como volumen; agregar un pais MUST implicar 0
  archivos de codigo cambiados y ninguna reconstruccion de imagen (MOD-2).
- Agregar un estado al ciclo de vida de un trabajo MUST requerir reiniciar unicamente
  `gestion_trabajos` (MOD-3).
- Una region MUST definirse una sola vez, en `infra/pulsar/comun.sh` (`crear_region`), usada tanto
  por la inicializacion como por el alta en caliente. Agregar una region MUST NOT tocar topicos
  existentes ni reiniciar servicios.
- Los consumidores que cubren varias regiones MUST suscribirse por patron (`evt-trabajo-.*`).

**Rationale**: las metricas de los escenarios de calidad (0 archivos, 0 servicios reiniciados) son
criterios de aceptacion del proyecto, no aspiraciones.

### V. Resiliencia por Diseno: Al-Menos-Una-Vez e Idempotencia
El sistema MUST asumir entrega al-menos-una-vez y MUST NOT perder ni duplicar trabajo tras una
caida.

- Todo handler de comandos y eventos MUST ser idempotente; la idempotencia vive en el comando,
  no en el transporte.
- Un evento sin destino conocido (por ejemplo, un cambio de estado de un trabajo sin seguimiento)
  MUST registrarse como huerfano y confirmarse, nunca descartarse en silencio.
- Un fallo del handler MUST hacer `negative_acknowledge`. El consumidor MUST reintentar la
  suscripcion ante fallos transitorios del broker y MUST NOT terminar por ello.
- Las suscripciones MUST pre-crearse en la infraestructura, de modo que los mensajes publicados
  antes de que un consumidor arranque se retengan para el.
- La politica de backlog MUST desalojar lo mas viejo en lugar de retener al productor, con la
  retencion dimensionada por encima de la cuota. La creacion automatica de topicos MUST estar
  deshabilitada en los namespaces `hogar-alpes/*`.
- Cada proceso MUST usar un solo cliente y un productor de Pulsar; MUST NOT abrir un cliente por
  mensaje. El estado compartido MUST protegerse con `threading.RLock`, no con `Lock`.
- Los eventos MUST publicarse con clave de particion `trabajo_id` y propiedades `partner_id`,
  `region` y `correlation_id`, para preservar el orden por trabajo y la trazabilidad.

**Rationale**: los escenarios de disponibilidad y escalabilidad exigen 0 errores durante la
caida, 100% de lo acumulado procesado y sin duplicados.

### VI. Verificacion Honesta (NON-NEGOTIABLE)
Una verificacion que pasa sin probar nada es peor que no tenerla. Toda prueba y todo script de
escenario MUST cumplir:

- Las aserciones MUST compararse contra literales, no contra atributos del objeto que se acaba de
  producir.
- La verificacion MUST ejercitar el camino real que recorre el escenario (por ejemplo, publicar un
  evento), no el que resulta facil de montar.
- Los scripts MUST releer del broker o de la base lo que crearon, en lugar de confiar en que
  ningun comando protesto.
- Los scripts de escenario MUST reportar cada metrica como PASA o FALLA en `docs/resultados/`.
- Lo que no se pudo ejecutar (por ejemplo, sin Docker o sin credenciales de AWS) MUST anotarse
  como pendiente, nunca como hecho.
- Un script que modifica el arbol de trabajo MUST abortar si el archivo afectado tiene cambios sin
  commitear.

**Rationale**: los tres defectos mas costosos del proyecto (contratos sin sobre, `Lock` no
reentrante, `vigencia_meses` perdida) pasaron pruebas que comparaban un valor contra si mismo o no
ejercitaban el camino real.

## Restricciones Tecnicas y de Despliegue

- Lenguaje y runtime: Python 3.11 (imagen `python:3.11-slim`); el target de version MUST NOT
  relajarse para acomodar un entorno de desarrollo.
- Mensajeria: Apache Pulsar, tenant `hogar-alpes`, tres namespaces, topicos particionados
  (4 particiones) por region: `cmd-trabajo-<r>` y `evt-trabajo-<r>`.
- Persistencia: PostgreSQL, una instancia por servicio.
- Todo el sistema MUST levantarse desde un clon limpio con `docker compose up -d --build`,
  incluida la topologia de Pulsar, sin intervencion manual. Las variables MUST traer un valor por
  defecto (`.env.example`).
- Las herramientas que corren desde el host (generador de carga, medicion de latencia) MUST usar
  `listener_name="external"`; los servicios dentro de Docker no.
- La creacion de tablas al arrancar MUST tolerar la carrera entre API y consumidor
  (`_crear_tablas()` con reintento).
- Metas de calidad medibles: consultas < 1 s con mas de 100.000 proveedores; latencia bajo 500 ms
  con degradacion menor al 10% durante una caida; duplicar capacidad de un servicio degrada su
  velocidad menos del 10%.
- Cada servicio MUST exponer `/health`. Los secretos MUST NOT commitearse (`.env` esta ignorado).

## Flujo de Desarrollo y Puertas de Calidad

- Todo cambio MUST ir en un Pull Request contra `main`; `docs/resultados` no se versiona.
- Los cambios de comportamiento MUST incluir pruebas `pytest` del servicio afectado, y la suite de
  los otros servicios MUST seguir en verde (regresion).
- Toda decision tomada durante la implementacion que no estuviera cerrada en el plan tecnico MUST
  anotarse en `docs/decisiones.md`, con su verificacion ejecutada.
- Los cambios a `contratos/` MUST pasar `herramientas/verificar_contratos.py`.
- Los cambios que afectan un escenario de calidad MUST ejecutar el script correspondiente en
  `escenarios/` (`mod-1.sh`, `mod-2.sh`, `mod-3.sh`, `escenario-6.sh`, `escenario-8.sh`,
  `esquemas.py`) o registrar explicitamente que quedo pendiente.
- Los atajos temporales (por ejemplo, publicar eventos sinteticos) MUST documentarse como
  temporales y retirarse cuando desaparezca la pieza que los hacia necesarios.
- Los desarrollos siguen el flujo Spec Kit (`/speckit-specify`, `/speckit-plan`, `/speckit-tasks`,
  `/speckit-implement`), y MUST verificar el cumplimiento de esta constitucion en el plan.

## Governance

Esta constitucion prevalece sobre cualquier otra practica del proyecto. Los principios marcados
MUST/MUST NOT son obligatorios; una excepcion MUST justificarse por escrito en `docs/decisiones.md`
con su alternativa descartada.

- **Enmiendas**: se proponen por Pull Request que modifica este archivo, con la justificacion,
  el impacto en las plantillas y guias dependientes, y la aprobacion de al menos un integrante
  del equipo distinto del autor.
- **Versionado** (semantico): MAJOR para eliminar o redefinir un principio de forma
  incompatible; MINOR para agregar un principio o seccion, o ampliar materialmente la guia;
  PATCH para aclaraciones, redaccion y correcciones no semanticas.
- **Revision de cumplimiento**: todo Pull Request y todo plan de Spec Kit MUST verificar el
  cumplimiento de los principios I a VI; la complejidad adicional MUST justificarse. Antes de
  cada entrega se revisa la constitucion contra `docs/decisiones.md` para detectar deriva.
- **Guia de trabajo en curso**: `README.md` (estructura y despliegue) y `docs/decisiones.md`
  (decisiones vivas de implementacion).

**Version**: 1.0.0 | **Ratified**: 2026-09-19 | **Last Amended**: 2026-09-19
