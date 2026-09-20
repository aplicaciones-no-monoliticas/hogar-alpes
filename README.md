# Hogar de los Alpes

Hogar de los Alpes conecta clientes con proveedores de servicios para el hogar
(plomería, electricidad, cerrajería, etc.). El sistema está dividido en
**cuatro servicios pequeños e independientes** que se avisan entre sí enviando
mensajes, en vez de llamarse directamente unos a otros. A esto se le llama
**arquitectura orientada a eventos**.

## Los cuatro servicios

| Servicio | Qué hace |
|---|---|
| `gestion_trabajos` | Recibe las solicitudes de trabajo, las registra y administra su ciclo de vida (creado, en ejecución, completado, etc.) |
| `operaciones` | Hace seguimiento a cada trabajo: le asigna una prioridad y un tiempo límite de atención |
| `acreditacion` | Administra qué proveedores están certificados, en qué categorías y desde cuándo — guarda el historial completo, no solo el estado actual |
| `emparejamiento` | Busca proveedores certificados y disponibles para asignarlos a un trabajo |

Cada servicio tiene su propia base de datos y nunca se comunica con otro por
llamadas directas (HTTP): todo lo que se avisan entre sí viaja por
**Apache Pulsar**, el sistema de mensajería del proyecto.

---

## El BFF: un solo punto de entrada

Además de los servicios de dominio hay un componente de **borde**, `bff`
(`servicios/bff/`), que es la puerta por la que pueden entrar los clientes:

- **Por qué existe.** Quien usa o prueba el sistema no debería tener que saber
  en qué puerto vive cada servicio. Con el BFF hace todas las peticiones contra
  **una sola dirección** (`http://localhost:8090`), y las consultas que antes
  exigían cuatro llamadas —por ejemplo «¿cómo va este trabajo?»
  (`GET /trabajos/{id}/completo`)— se resuelven con una.
- **Trazabilidad.** El BFF crea un código único por petición
  (`X-Correlation-Id`), lo devuelve en toda respuesta y todos los servicios lo
  copian en sus mensajes y en sus registros: una sola búsqueda en los registros
  reconstruye lo que le pasó a una petición.
- **Es una puerta adicional, no obligatoria.** **Sigue siendo válido llamar
  directo a cada servicio** (8000–8003), y así es como se miden los escenarios
  de calidad. El BFF no tiene base de datos, no habla con Pulsar y no guarda
  estado; los servicios de dominio siguen sin llamarse entre sí, y solo el BFF
  hace llamadas HTTP hacia adentro.

Rutas, respuestas compuestas, configuración y cómo seguir una petición por los
registros: [`servicios/bff/README.md`](servicios/bff/README.md).

---

## Escenarios de calidad a probar

El proyecto debe demostrar que el sistema cumple con estas cinco propiedades:

| Escenario | Qué se prueba | Métrica esperada |
|---|---|---|
| **Cambiar cómo se guardan los datos** | Reemplazar la forma en que Gestión de Trabajos guarda su información | **0** archivos de las reglas de negocio cambiados |
| **Agregar un país nuevo** | Sumar un país con sus propias reglas (categorías y urgencias permitidas) | **0** archivos de código cambiados, sin reconstruir el servicio |
| **Agregar un estado nuevo** | Sumar un paso nuevo al ciclo de vida de un trabajo | **0** servicios reiniciados aparte de Gestión de Trabajos |
| **Disponibilidad** | Un servicio deja de funcionar 30 minutos o más | **0** errores en el resto del sistema durante la caída · el tiempo de respuesta no sube más del **10%** (se mantiene bajo **500 ms**) · al reactivarse, se procesa el **100%** de lo acumulado, sin duplicados |
| **Escalabilidad** | El sistema recibe una carga alta de trabajos y consultas | Al duplicar la capacidad de un servicio, su velocidad casi se duplica (degradación menor al **10%**) · las consultas responden en menos de **1 segundo** con más de **100.000** proveedores registrados · agregar una región nueva no afecta a las que ya estaban activas |

---

## Estructura del proyecto

```
hogar-alpes/
├── servicios/          código de los cuatro microservicios y del BFF (punto de entrada)
├── contratos/            la forma de los mensajes que viajan entre servicios
├── infra/                configuración de la mensajería y del despliegue
├── escenarios/           scripts para poner a prueba cada escenario de calidad
├── herramientas/         scripts de apoyo: generar carga, medir tiempos de respuesta
├── postman/              colección de pruebas para la API de cada servicio
├── docs/                 documentación del proyecto
└── docker-compose.yml    receta para levantar todo el sistema de una vez
```

Cada servicio, dentro de `servicios/<nombre>/`, sigue la misma organización
interna: sus reglas de negocio, sus casos de uso y su conexión con la base de
datos y con Pulsar están separados en carpetas distintas, para que cambiar una
parte no obligue a tocar las demás.

---

## Cómo desplegar los servicios

1. Tener **Docker** instalado (con el complemento de Compose).
2. Clonar el repositorio.
3. Opcional: copiar `.env.example` a `.env` — todas las variables ya traen un valor por defecto.
4. Levantar todo el sistema con un solo comando:

   ```bash
   docker compose up -d --build
   ```

5. Esperar unos minutos mientras se construyen las imágenes y arranca la mensajería.
6. Verificar que cada servicio responda:

   | Servicio | Dirección |
   |---|---|
   | `gestion_trabajos` | http://localhost:8000/health |
   | `operaciones` | http://localhost:8001/health |
   | `acreditacion` | http://localhost:8002/health |
   | `emparejamiento` | http://localhost:8003/health |

**Para probar la escalabilidad:** se puede levantar más copias de un servicio
sin apagar el resto del sistema:

```bash
docker compose up -d --scale emparejamiento-andina=4
```

**Para agregar una región nueva** (por ejemplo, para atender un país en otra
zona) sin apagar nada:

```bash
docker compose run --rm pulsar-config bash /infra/agregar-region.sh conosur
```

---

## Flujos que se van a probar

**1. Crear un trabajo.** Un cliente pide un trabajo → Gestión de Trabajos lo
registra → avisa automáticamente a Operaciones (para hacerle seguimiento) y a
Emparejamiento (para buscarle candidatos). Gestión de Trabajos no espera
respuesta de ninguno de los dos: simplemente avisa y sigue.

Solicitud de ejemplo que inicia el flujo:

```bash
curl -X POST http://localhost:8000/trabajos \
  -H "Content-Type: application/json" \
  -d '{
    "categoria": "PLOMERIA",
    "urgencia": "ALTA",
    "pais": "CO",
    "ciudad": "Bogota",
    "direccion": "Cra 7 # 71-21",
    "descripcion": "Fuga de agua en la cocina"
  }'
```

**2. Acreditar un proveedor.** Se aprueba la certificación de un proveedor →
Acreditación guarda el hecho en su historial → avisa a Emparejamiento, que
actualiza su lista de proveedores disponibles para usarla en búsquedas
futuras.

Solicitud de ejemplo que inicia el flujo:

```bash
curl -X POST http://localhost:8002/acreditaciones \
  -H "Content-Type: application/json" \
  -d '{
    "proveedor_id": "prov-001",
    "pais": "CO",
    "ciudad": "Bogota",
    "categorias": ["PLOMERIA"],
    "nivel": "ORO",
    "vigencia_meses": 12
  }'
```

Luego se aprueba con `PUT /acreditaciones/prov-001/aprobar`.

**3. Disponibilidad (escenario de caída).** Se detiene Operaciones mientras se
siguen creando trabajos. Se comprueba que Gestión de Trabajos sigue
respondiendo con normalidad, y que al reactivar Operaciones esta procesa todo
lo acumulado, sin perder ni repetir ningún trabajo.

```bash
docker compose stop operaciones-consumidor
# mientras tanto, se repite la misma solicitud de "crear un trabajo" de arriba
docker compose start operaciones-consumidor
```

**4. Escalabilidad (escenario de crecimiento).** Se genera una carga alta de
trabajos y de acreditaciones. Se agregan más copias de Emparejamiento y una
región nueva mientras el sistema sigue en funcionamiento, y se comprueba que
las consultas siguen respondiendo rápido y que las regiones que ya estaban
activas no se interrumpen.

```bash
docker compose up -d --scale emparejamiento-andina=4
curl "http://localhost:8003/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota"
```

---

## Cómo se prueban los escenarios

Cada escenario de calidad tiene su propio script en `escenarios/`, que lo
pone a prueba de principio a fin sin que nadie tenga que revisarlo a mano:
hace los cambios necesarios, genera el tráfico que hace falta, y al final
dice si cada métrica se cumplió o no.

| Script | Qué hace |
|---|---|
| `mod-1.sh` | Reinicia Gestión de Trabajos guardando la información en memoria en vez de en la base de datos, y comprueba que las reglas de negocio no tuvieron que cambiar ni un archivo |
| `mod-2.sh` | Agrega un país nuevo al archivo de reglas regionales, reinicia el servicio y comprueba que el país nuevo funciona sin tocar ni un archivo de código |
| `mod-3.sh` | Agrega un estado nuevo al ciclo de vida de un trabajo, redespliega solo Gestión de Trabajos, y comprueba que Operaciones y Emparejamiento siguen funcionando sin reiniciarse |
| `escenario-6.sh` | Detiene Operaciones, genera trabajos durante varios minutos y, al reactivarlo, comprueba que procesó todo lo acumulado sin perder ni repetir nada |
| `escenario-8.sh` | Carga miles de acreditaciones y de trabajos, agrega más copias de Emparejamiento y una región nueva, y mide si las consultas y el procesamiento se mantienen rápidos |
| `bff.sh` | Con el sistema levantado, comprueba el BFF: detiene un servicio de verdad y verifica el `503` y que los demás siguen; reconstruye una petición con una sola búsqueda en los registros de todos los servicios; inspecciona mensajes reales del broker; y confirma que la clave de partición no cambió |
| `esquemas.py` | Agrega un campo nuevo a un mensaje y comprueba que el sistema lo acepta; luego intenta un cambio incompatible y comprueba que el sistema lo rechaza |

Al terminar, cada script deja un archivo en `docs/resultados/` con el
resultado de cada métrica marcado como **PASA** o **FALLA**, listo para
revisar sin tener que repetir la prueba.
