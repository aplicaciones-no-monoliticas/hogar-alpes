# Hogar de los Alpes

Entrega 4 (MISW4406 · Diseño y Construcción de Soluciones No Monolíticas):
**cuatro microservicios** que se comunican exclusivamente por comandos y
eventos sobre **Apache Pulsar**, cada uno con su propia base de datos.

La justificación arquitectónica completa está en `docs/`:
[`01-especificacion.md`](docs/01-especificacion.md) (qué se construye y cómo
se verifica), [`02-plan-tecnico.md`](docs/02-plan-tecnico.md) (cómo, técnico)
y [`decisiones.md`](docs/decisiones.md) (lo que cambió durante la
implementación y por qué).

---

## Los cuatro servicios

| Servicio | Contexto acotado | Persistencia | Puerto (local) |
|---|---|---|---|
| `gestion_trabajos` | Gestión de Trabajos — el núcleo | CRUD PostgreSQL | 8000 |
| `operaciones` | Operaciones y Calidad — reactor puro | CRUD PostgreSQL | 8001 |
| `acreditacion` | Acreditación — subdominio núcleo | **Event Sourcing** PostgreSQL | 8002 |
| `emparejamiento` | Emparejamiento y Publicación | CRUD (proyección + escritura) PostgreSQL | 8003 |

Cada uno vive en `servicios/<nombre>/`, es autocontenido (su Dockerfile, sus
dependencias, su seedwork copiado — decisión `TO-7`) y arranca como **dos
procesos** de la misma imagen: `api` (HTTP, gunicorn) y `consumidor` (Pulsar).
Eso es lo que permite escalar consumidores sin tocar el puerto HTTP
(escenario 8) y detener un reactor sin tumbar su API (escenario 6).

```
                         Apache Pulsar (clúster propio)
        cmd-trabajo-*         evt-trabajo-*        evt-acreditacion
             │                  │    │                    │
             ▼                  ▼    ▼                    ▼
  ┌────────────────┐   ┌─────────────┐   ┌──────────────┐   ┌───────────────┐
  │ gestion_trabajos│──▶│ operaciones │   │ acreditacion │──▶│ emparejamiento│
  │  (CRUD)         │   │  (CRUD)     │   │ (Event Src.) │   │  (proyección) │
  └────────────────┘   └─────────────┘   └──────────────┘   └───────────────┘
```

Ningún servicio le habla a otro por HTTP (RNF-1): cada red Docker conecta un
servicio solo con el broker y con **su propia** base de datos (`docker-compose.yml`,
INF-5/CA-T1).

---

## Cómo levantarlo

Requiere Docker y el plugin de Compose. Desde un clon limpio:

```bash
cp .env.example .env      # opcional: todas las variables tienen valor por defecto
docker compose up -d --build
```

Esto levanta, en orden: ZooKeeper, dos *bookies* y dos *brokers* de Pulsar,
`pulsar-config` (crea tenant/namespaces/tópicos/suscripciones, idempotente),
las cuatro bases de datos y los ocho procesos de servicio (api + consumidor ×
4). La primera vez tarda unos minutos en construir las imágenes.

```bash
docker compose ps                 # todo en `healthy` o `running`
curl localhost:8000/health        # gestion-trabajos
curl localhost:8001/health        # operaciones
curl localhost:8002/health        # acreditacion
curl localhost:8003/health        # emparejamiento
```

Para agregar una región en caliente (CA-8.4):

```bash
docker compose run --rm pulsar-config bash /infra/agregar-region.sh conosur
docker compose --profile conosur up -d emparejamiento-conosur
```

### Pruebas

Cada servicio tiene su propia suite, sin depender de un broker real (los
`tests/conftest.py` reemplazan la publicación por un no-op):

```bash
for s in gestion_trabajos operaciones acreditacion emparejamiento; do
  (cd servicios/$s && pip install -r requirements.txt -q && pytest -q)
done
```

### Postman

`postman/hogar-alpes.postman_collection.json` + entornos `local`
(`hogar-alpes.postman_environment.json`) y `aws`
(`hogar-alpes-aws.postman_environment.json`):

```bash
npx newman run postman/hogar-alpes.postman_collection.json \
  -e postman/hogar-alpes.postman_environment.json
```

---

## Escenarios de calidad — un comando por escenario (RNF-8)

Cada script imprime **PASA/FALLA por criterio de aceptación** y guarda su
salida en `docs/resultados/`.

| Escenario | Script | Qué demuestra |
|---|---|---|
| **6** · Disponibilidad | `escenarios/escenario-6.sh` | El reactor de Operaciones cae ≥ 30 min: Gestión de Trabajos no se entera, el backlog se retiene y se drena al 100% |
| **8** · Escalabilidad | `escenarios/escenario-8.sh` | Throughput ~lineal 1→2 réplicas, región nueva sin interrumpir las activas, consulta < 1 s con ≥ 100.000 proveedores |
| **MOD-1** | `escenarios/mod-1.sh` | Reemplazar el adaptador de persistencia de Gestión de Trabajos por configuración, sin tocar `dominio/` ni `aplicacion/` |
| **MOD-2** | `escenarios/mod-2.sh` | País nuevo por el sidecar de reglas regionales, sin reconstruir la imagen |
| **MOD-3** | `escenarios/mod-3.sh` | Estado nuevo en el ciclo de vida: se redespliega solo Gestión de Trabajos, Operaciones y Emparejamiento ni se reinician |
| Esquemas | `escenarios/esquemas.py` | CA-E1 (campo opcional aceptado) y CA-E2 (cambio incompatible rechazado) contra el Schema Registry de Pulsar |

Herramientas de apoyo, en `herramientas/`: `generador_carga.py` (publica
trabajos a una tasa/tiempo dados), `medir_latencia.py` (p50/p95/p99),
`cargar_acreditaciones.py` (100.000 acreditaciones), `verificar_contratos.py`
y `spike_esquemas.py` (los instrumentos de INF-0 y CON-1).

**Estado de las corridas formales:** ver `docs/resultados/` y
`docs/decisiones.md` — varios escenarios se escribieron y verificaron con
`pytest`, pero su corrida de punta a punta contra un clúster real (o contra
AWS, para DEP-2) puede seguir pendiente si no se ha ejecutado todavía en este
entorno; el estado exacto por tarea está en `docs/03-tareas.md`.

---

## Topología de datos y esquemas

- **Descentralizada**: una instancia de PostgreSQL por servicio (§7 de la
  especificación), justificada contra los escenarios 6 y 8, no por dogma.
- **Avro + Schema Registry de Pulsar**, `FULL_TRANSITIVE`. Todo campo se
  declara `Tipo(default=None, required_default=True)` — sin eso el broker
  rechaza cualquier evolución (hallazgo de INF-0, `docs/decisiones.md`).
- Los contratos canónicos viven en `contratos/v1/`; cada servicio guarda su
  propia copia del lado que usa (productor o consumidor) — decisión `TO-7`,
  no una biblioteca compartida.

---

## Estructura del repositorio

```
hogar-alpes/
├── servicios/            gestion_trabajos · operaciones · acreditacion · emparejamiento
│   └── _plantilla/       la carpeta que se copia para levantar un servicio nuevo
├── contratos/v1/          esquemas Avro canónicos (CON-1)
├── infra/
│   ├── pulsar/            inicializar.sh · agregar-region.sh · topologia.env
│   ├── sidecar/            reglas_regionales.json — el volumen de MOD-2
│   └── aws/                user-data.sh · README.md del despliegue (DEP-1)
├── escenarios/             un script por escenario (RNF-8)
├── herramientas/           generador de carga, medición, carga masiva, verificación
├── postman/                colección + entornos local/aws
├── docs/                   especificación · plan técnico · tareas · decisiones · resultados
├── docker-compose.yml
└── .env.example
```

---

## Documento de actividades

`docs/actividades.md` enlaza cada tarea de `docs/03-tareas.md` con los
commits y PR que la implementaron, por integrante (requisito de la rúbrica:
contribuciones equitativas y verificables).
