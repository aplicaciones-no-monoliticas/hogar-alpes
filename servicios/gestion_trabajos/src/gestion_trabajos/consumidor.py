"""Punto de entrada del proceso consumidor (`MODO=consumidor`).

Corre como proceso propio, no como hilo dentro de la API. Tres razones:

1. **Escenario 8**: se escalan los consumidores con `docker compose --scale`, sin
   chocar con el puerto HTTP de la API.
2. **Escenario 6**: se puede detener el consumo sin tumbar la API del servicio.
3. Elimina un defecto real: el hilo arrancaba dentro de `create_app`, así que
   con el recargador de Flask o con varios workers de gunicorn podía quedar
   duplicado, consumiendo el mismo comando dos veces.
"""
import logging
import os


def main():
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(name)s | %(message)s',
    )

    from gestion_trabajos import crear_app
    from gestion_trabajos.modulos.trabajos.infraestructura.consumidores import (
        suscribirse_a_comandos,
    )

    # La aplicación se crea para tener contexto de base de datos, no para servir
    # HTTP: este proceso no escucha en ningún puerto.
    app = crear_app()
    logging.getLogger(__name__).info('Proceso consumidor de Gestión de Trabajos')
    suscribirse_a_comandos(app)


if __name__ == '__main__':
    main()
