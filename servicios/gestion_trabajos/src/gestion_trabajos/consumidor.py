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
    from gestion_trabajos.seedwork.infraestructura import correlacion

    correlacion.instalar_registro()
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(name)s | cid=%(correlation_id)s%(campos)s | %(message)s',
    )

    import threading

    from gestion_trabajos import crear_app
    from gestion_trabajos.modulos.trabajos.infraestructura.consumidores import (
        suscribirse_a_comandos,
        suscribirse_saga_acreditacion,
        suscribirse_saga_emparejamiento,
    )

    # La aplicación se crea para tener contexto de base de datos, no para servir
    # HTTP: este proceso no escucha en ningún puerto.
    app = crear_app()
    logging.getLogger(__name__).info('Proceso consumidor de Gestión de Trabajos')

    # Saga (Entrega 5): dos suscripciones nuevas, cada una en su propio hilo,
    # igual que en Emparejamiento y Acreditación.
    hilos = [
        threading.Thread(target=suscribirse_a_comandos, args=(app,), daemon=True),
        threading.Thread(target=suscribirse_saga_emparejamiento, args=(app,), daemon=True),
        threading.Thread(target=suscribirse_saga_acreditacion, args=(app,), daemon=True),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()


if __name__ == '__main__':
    main()
