# Plantilla de servicio

Base común de los microservicios de Hogar de los Alpes. **Se copia, no se importa.**

Esa es la decisión `TO-7` de la Entrega 2: un paquete compartido volvería a acoplar los servicios en tiempo de compilación —un arreglo obligaría a redesplegarlos todos a la vez— y reintroduciría el punto de sensibilidad `PS-8`. Se acepta duplicar para conservar el despliegue independiente.

## Cómo se crea un servicio

```bash
cp -r servicios/_plantilla servicios/<nombre>
cd servicios/<nombre>
git mv src/servicio_plantilla src/<nombre>
grep -rl servicio_plantilla . | xargs sed -i '' "s/servicio_plantilla/<nombre>/g"
```

En macOS el `sed` lleva `-i ''`; en Linux es `sed -i`.

**El seedwork no menciona el nombre del paquete.** Sus imports hacia `config/` son relativos (`from ...config.uow import ...`), así que renombrar la carpeta basta. Es una mejora sobre la primera versión de Gestión de Trabajos, que tenía la ruta absoluta escrita en el seedwork.

## Qué trae

```
src/servicio_plantilla/
├── seedwork/          Entidad · AgregacionRaiz · ObjetoValor · EventoDominio
│   ├── dominio/       ReglaNegocio · Repositorio · Mapeador · Fabrica
│   ├── aplicacion/    Comando · Query · handlers · despacho CQS
│   └── infraestructura/  UnidadDeTrabajo · Despachador
├── config/            db · broker (cliente y productor reutilizados) · uow
├── api/               solo /health; cada servicio agrega sus rutas
├── consumidor.py      bucle de consumo con reintento
└── modulos/           vacío: aquí va el dominio del servicio
```

## Lo que hay que escribir en cada servicio

1. `modulos/<contexto>/dominio/` — agregación, objetos valor, reglas, puertos.
2. `modulos/<contexto>/aplicacion/` — comandos, consultas, handlers.
3. `modulos/<contexto>/infraestructura/` — repositorio, mapeadores, esquemas de `CON-1`.
4. En `crear_app()`, registrar el blueprint y las tablas del servicio.
5. En `consumidor.py`, declarar a qué se suscribe.

## Dos defectos que esta plantilla ya no tiene

Los encontramos ejecutando INF-0 e INF-2, y están documentados en `docs/decisiones.md`:

- **El despachador no abre un cliente por mensaje** (brecha `G-3a`). Un cliente y un productor por proceso.
- **El consumidor no se muere ante un fallo transitorio.** En la primera versión, un `TopicNotFound` al arrancar terminaba el hilo para siempre y el servicio seguía respondiendo `202` sin consumir nada. Aquí el bucle reintenta.

## Los dos modos del proceso

La misma imagen arranca como API o como consumidor, según `MODO`:

```bash
MODO=api         # gunicorn, puerto 5000
MODO=consumidor  # python -m <nombre>.consumidor
```

Sigue siendo **un** microservicio: mismo código y misma base de datos, con dos roles que escalan por separado. Es lo que permite escalar consumidores sin chocar puertos (escenario 8) y detener el reactor sin tumbar su API (escenario 6).
