# Sidecar de reglas regionales

`reglas_regionales.json` de este directorio es la fuente **externa** que lee
`SidecarReglasRegionales` (`servicios/gestion_trabajos/.../reglas_regionales.py`)
en `docker compose`, montado como volumen en `gestion-trabajos` y
`gestion-trabajos-consumidor` (`RUTA_REGLAS_REGIONALES`).

Antes de esto el archivo vivía **dentro** de la imagen (`COPY src/`), así que
"agregar un país" habría exigido reconstruir la imagen — contradice la medida
del escenario 2 (`CA-M2`: 0 archivos de código cambiados). Con el volumen, el
archivo del servicio (`.../infraestructura/reglas_regionales.json`) queda
como el valor por defecto para quien corra el servicio fuera de Compose (por
ejemplo, `pytest`), y este es el que manda en el sistema desplegado.

**Agregar un país** (lo que hace `escenarios/mod-2.sh`):

1. Editar este archivo — agregar la clave del país con sus `categorias` y
   `urgencias`.
2. `docker compose restart gestion-trabajos gestion-trabajos-consumidor` —
   la configuración se lee una sola vez por proceso (`@lru_cache`), así que
   "reiniciar el sidecar" es reiniciar el proceso, no recargar en caliente.

Cero archivos de `servicios/gestion_trabajos` cambiados.
