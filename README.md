# Hogar de los Alpes — Servicio Gestión de Trabajos

Implementación de referencia de la **Entrega 3** (MISW4406 · Diseño y Construcción de
Soluciones No Monolíticas). Es uno de los nueve micro-servicios de la arquitectura
objetivo diseñada en las entregas 1 y 2, construido con DDD y una arquitectura de
micro-servicios basada en eventos.

Se eligió **Gestión de Trabajos** porque es el artefacto declarado en los escenarios de
calidad 1, 2, 3 y 7: la implementación queda trazada contra lo ya documentado.

---

## Escenarios de calidad que este código prepara

| # | Atributo | Escenario | Dónde se ve en el código |
|---|---|---|---|
| 1 | Modificabilidad | Reemplazar el adaptador de persistencia sin tocar el dominio | El puerto `dominio/repositorios.py` y el adaptador `infraestructura/repositorios.py`. Migrar de motor = otra clase que implemente el puerto |
| 2 | Modificabilidad | Reglas de un país nuevo sin redesplegar el servicio | `infraestructura/reglas_regionales.py` + `reglas_regionales.json`. El dominio nunca sabe en qué país corre |
| 3 | Modificabilidad | Agregar un estado al ciclo de vida sin afectar a otros servicios | `dominio/objetos_valor.py` — el grafo `TRANSICIONES`. `EN_VERIFICACION` ya está ahí como prueba |
| 7 | Escalabilidad | Absorber un pico ×4 sin rechazar solicitudes | `POST /trabajos` responde `202`; el consumidor de `cmd-trabajo` drena a su ritmo |

---

## Arquitectura

Hexagonal, tres capas, con la flecha de dependencia siempre hacia adentro:

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
        │ eventos, reglas, fábricas, PUERTOS        │   (inversión de dependencias)
        └───────────────────────────────────────────┘
```

El **dominio no importa nada de infraestructura**. Las pruebas de `tests/test_dominio_trabajo.py`
corren sin base de datos ni broker: si algún día necesitaran levantar Postgres, el
aislamiento estaría roto.

### Los dos módulos y cómo se hablan

```
  módulo TRABAJOS                                  módulo OPERACIONES
  ───────────────                                  ──────────────────
  Trabajo (agregación raíz)                        SeguimientoOperativo (agregación raíz)
  └─ SubTrabajo (entidad interna)
                    │
                    │  TrabajoCreado / EstadoTrabajoCambiado
                    │  (evento de DOMINIO, en proceso)
                    └──────────────────────────────────►  abre el seguimiento
                                                          y aplica su política de SLA
```

`operaciones` **no importa una sola línea de `trabajos`**. Se suscribe a la señal
`TrabajoCreadoDominio` que emite la Unidad de Trabajo y lee el evento por atributos.
Consecuencia: agregar un estado nuevo al ciclo de vida no lo rompe.

### Eventos: quién sale cuándo

La Unidad de Trabajo (`seedwork/infraestructura/uow.py`) decide el momento:

| Tipo | Cuándo | A dónde | Versionado |
|---|---|---|---|
| **Dominio** | antes del commit | en proceso, entre módulos | no |
| **Integración** | después del commit | tópico `evt-trabajo` del broker | sí, `schema/v1` |

El orden no es un detalle: un evento de integración afirma un hecho hacia afuera. Si
saliera antes del commit y la transacción fallara, se habría anunciado algo que nunca
ocurrió.

### CQS

| | Escritura | Lectura |
|---|---|---|
| Objeto | `Comando` | `Query` |
| Despacho | `ejecutar_comando` (`singledispatch`) | `ejecutar_query` |
| Devuelve | nada — solo el id | datos |
| Ruta HTTP | `POST /trabajos` → `202` | `GET /trabajos/<id>` → `200` |

---

## Estructura del proyecto

```
src/gestion_trabajos/
├── seedwork/                  copia versionada, NO biblioteca compartida (PS-8 / TO-7)
│   ├── dominio/               Entidad · AgregacionRaiz · ObjetoValor · EventoDominio
│   │                          ReglaNegocio · Repositorio · Fabrica · Mapeador
│   ├── aplicacion/            Comando · Query · handlers · dispatchers CQS
│   └── infraestructura/       UnidadDeTrabajo · Despachador · esquema CloudEvents
├── modulos/
│   ├── trabajos/              MÓDULO 1 — el núcleo
│   │   ├── dominio/           Trabajo, SubTrabajo, EstadoTrabajo, reglas, PUERTOS
│   │   ├── aplicacion/        comandos/ · queries/ · mapeadores · handlers
│   │   └── infraestructura/   repositorio Postgres · sidecar regional · Avro v1
│   └── operaciones/           MÓDULO 2 — reacciona por eventos de dominio
├── api/                       adaptador HTTP
└── config/                    db · broker · binding de la UoW
```

El **seedwork es una copia de este servicio**, no una biblioteca compartida. Es la
decisión `TO-7` de la Entrega 2: se acepta duplicar para no reintroducir acoplamiento en
tiempo de compilación entre los nueve servicios.

---

## Cómo levantarlo

```bash
docker compose up --build
```

Levanta PostgreSQL, Apache Pulsar (standalone) y el servicio en `http://localhost:5000`.

### Local, sin Docker

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d postgres pulsar

export PYTHONPATH=src
export DATABASE_URI=postgresql+psycopg2://hogaralpes:hogaralpes@localhost:5432/gestion_trabajos
export FLASK_APP=gestion_trabajos
flask run
```

### Pruebas

```bash
pytest
```

---

## API

| Verbo | Ruta | Qué hace |
|---|---|---|
| `POST` | `/trabajos` | Comando `CrearTrabajo`. Responde **`202 Accepted`** |
| `GET` | `/trabajos/<id>` | Consulta `ObtenerTrabajo` |
| `GET` | `/trabajos?estado=CREADO` | Consulta `ObtenerTrabajosPorEstado` |
| `PUT` | `/trabajos/<id>/estado` | Comando `CambiarEstadoTrabajo` |
| `GET` | `/trabajos/<id>/seguimiento` | Lee el módulo `operaciones` — prueba de que el evento de dominio cruzó |
| `GET` | `/health` | Estado del servicio |

### Recorrido de demostración

```bash
# 1. Crear un trabajo de siniestro. Responde 202 con el id.
curl -s -X POST localhost:5000/trabajos -H 'Content-Type: application/json' -d '{
  "canal": "B2B2C", "partner_id": "seguros-alpes", "referencia_externa": "SIN-99123",
  "categoria": "SINIESTRO_GRANIZO", "urgencia": "CRITICA",
  "pais": "CO", "ciudad": "Bogota", "direccion": "Cra 7 # 71-21",
  "descripcion": "Granizada: techo perforado" }'

# 2. Leerlo (lado de consulta del CQS)
curl -s localhost:5000/trabajos/<ID>

# 3. El módulo `operaciones` ya abrió su seguimiento con prioridad P1,
#    solo porque recibió el evento de dominio. Nunca leyó la tabla de trabajos.
curl -s localhost:5000/trabajos/<ID>/seguimiento

# 4. Transición válida
curl -s -X PUT localhost:5000/trabajos/<ID>/estado \
  -H 'Content-Type: application/json' -d '{"estado":"EMPAREJANDO"}'

# 5. Transición inválida -> 409, la rechaza el objeto valor EstadoTrabajo
curl -s -X PUT localhost:5000/trabajos/<ID>/estado \
  -H 'Content-Type: application/json' -d '{"estado":"COMPLETADO"}'

# 6. Categoría que no aplica en México -> 400, la rechaza el sidecar regional
curl -s -X POST localhost:5000/trabajos -H 'Content-Type: application/json' -d '{
  "categoria": "SINIESTRO_GRANIZO", "urgencia": "ALTA",
  "pais": "MX", "ciudad": "CDMX", "direccion": "Reforma 100" }'
```

---

## Trazabilidad con las entregas anteriores

| Decisión de este código | Origen |
|---|---|
| `SubTrabajo` dentro del límite de `Trabajo` | `PS-9` — Entrega 2, HDA-004. Se congela aquí la decisión que estaba abierta |
| Seedwork copiado, no compartido | `PS-8` / `TO-7` — Entrega 2, HDA-002 |
| Sidecar regional como cliente en Infraestructura | HDA-002 — el dominio no sabe en qué país corre |
| Eventos nombrados en pretérito (`evt.trabajo.*`) | HDA-003 — convención de la vista funcional C&C |
| `202 Accepted` en la creación | `PS-6` — falsificación de sincronía. Sin polling |
| Puerto de repositorio + inversión de dependencias | `PS-7` — el aislamiento depende de que se respeten los puertos |

---

## Alcance y límites conocidos

La guía de la entrega es explícita: *«NO se espera tener el servicio completamente
desarrollado, solo los comandos, consultas e infraestructura necesaria para satisfacer
los futuros escenarios de calidad»*. Lo que queda deliberadamente fuera:

- **`PS-7` no se hace cumplir automáticamente.** La regla «el dominio no importa
  infraestructura» hoy la sostienen la revisión de código y las pruebas de dominio. La
  Entrega 2 propone reforzarla con pruebas de arquitectura que fallen el build.
- **El sidecar regional corre en proceso.** Lee un JSON en vez de hablar con un sidecar
  desplegado aparte. El puerto ya está: cambiar el adaptador no toca el dominio.
- **Sin idempotencia por identificador de correlación** en el consumidor de comandos. Es
  el riesgo que el escenario 5 identifica para el tópico de retry.
- **Sin particionamiento de tópicos.** Es la decisión central del escenario 8 y es de
  configuración del broker, no de este código.
