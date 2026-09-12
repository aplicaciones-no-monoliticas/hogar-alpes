# Topología de mensajería

Todo lo que existe en el broker se crea desde aquí, con scripts versionados e idempotentes. Nada se crea a mano ni por accidente: los namespaces tienen la **creación automática de tópicos deshabilitada**, así que un nombre mal escrito falla en lugar de producir un tópico fantasma sin particiones ni suscripciones.

| Archivo | Qué hace |
|---|---|
| `topologia.env` | Fuente única: tenant, namespaces, regiones, particiones y políticas |
| `comun.sh` | Funciones compartidas y **la única definición de qué lleva una región** |
| `inicializar.sh` | Crea la topología completa. Se puede correr las veces que haga falta |
| `agregar-region.sh` | Agrega una región en caliente (INF-4, escenario 8) |

```bash
docker compose run --rm pulsar-config                        # topología completa
docker compose run --rm pulsar-config \
    bash /infra/agregar-region.sh conosur                     # región en caliente

PULSAR_ADMIN_URL=http://localhost:8080 bash inicializar.sh    # o desde el host
```

**Por qué `comun.sh`:** la forma de una región se define **una sola vez**, en `crear_region`. Si el alta en caliente creara tópicos o suscripciones distintas de las que crea la inicialización, la región nueva quedaría sutilmente rota y el escenario 8 estaría midiendo otra cosa.

Los dos scripts **verifican contra el broker** lo que crearon, en vez de confiar en que ningún comando protestó. Es la lección de INF-3: durante dos corridas una política no existía y mandaba el valor por defecto, sin que nada lo delatara.

## Qué queda creado

| Namespace | Tópicos (4 particiones cada uno) | Suscripciones pre-creadas |
|---|---|---|
| `hogar-alpes/trabajos` | `cmd-trabajo-{región}` · `evt-trabajo-{región}` | `gestion-trabajos` · `operaciones` · `emparejamiento-{región}` |
| `hogar-alpes/acreditacion` | `cmd-acreditacion` · `evt-acreditacion` | `acreditacion` · `emparejamiento-proyeccion` |
| `hogar-alpes/emparejamiento` | `evt-emparejamiento` | ninguna: nadie lo consume en la Entrega 4 |

Regiones iniciales: `andina` y `norteamerica`. **`conosur` no se crea aquí**: se agrega en caliente durante el escenario 8 para medir que las regiones activas no se interrumpen (CA-8.4).

## Las dos decisiones que sostienen el escenario 6

**Las suscripciones se crean por adelantado.** En Pulsar, un mensaje publicado en un tópico sin suscripciones no se retiene para nadie. Si Operaciones nunca hubiera arrancado, sus eventos simplemente no existirían cuando por fin lo hiciera. Con la suscripción pre-creada, el backlog se acumula desde el primer mensaje.

**La cuota de backlog desaloja, no retiene al productor.** Es la diferencia entre *«el consumidor se atrasó»* y *«el productor se bloqueó»*. Con la política que retiene al productor, una caída larga del reactor degradaría a Gestión de Trabajos: exactamente lo que el escenario prohíbe. El costo aceptado es perder eventos si la caída supera la ventana, un riesgo que la Entrega 3 declaró de forma explícita.

Y una precisión que conviene tener a la mano en la sustentación: **la «ventana de retención» del escenario la fijan el TTL y la cuota, no la política que Pulsar llama `retention`**, que solo aplica a los mensajes ya confirmados.
