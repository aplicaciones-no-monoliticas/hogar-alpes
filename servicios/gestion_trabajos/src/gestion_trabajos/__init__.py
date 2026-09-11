"""Servicio Gestión de Trabajos — Hogar de los Alpes.

Application factory. El orden de importación importa: los módulos de handlers se
importan explícitamente para que sus `dispatcher.connect` queden registrados
antes de atender el primer request.
"""
import logging
import os
import threading

from flask import Flask, jsonify


def importar_modelos_alchemy():
    import gestion_trabajos.modulos.trabajos.infraestructura.dto  # noqa: F401
    import gestion_trabajos.modulos.operaciones.infraestructura.dto  # noqa: F401


def registrar_handlers():
    """Suscribe los módulos a los eventos de dominio y de integración."""
    import gestion_trabajos.modulos.operaciones.aplicacion.handlers  # noqa: F401
    import gestion_trabajos.modulos.trabajos.aplicacion.handlers  # noqa: F401


def registrar_comandos_y_queries():
    """Fuerza el registro en los `singledispatch` de comandos y consultas."""
    import gestion_trabajos.modulos.trabajos.aplicacion.comandos.cambiar_estado_trabajo  # noqa: F401
    import gestion_trabajos.modulos.trabajos.aplicacion.comandos.crear_trabajo  # noqa: F401
    import gestion_trabajos.modulos.trabajos.aplicacion.queries.obtener_trabajo  # noqa: F401
    import gestion_trabajos.modulos.trabajos.aplicacion.queries.obtener_trabajos_por_estado  # noqa: F401
    import gestion_trabajos.modulos.operaciones.aplicacion.queries  # noqa: F401


def comenzar_consumidor(app):
    from gestion_trabajos.modulos.trabajos.infraestructura.consumidores import (
        suscribirse_a_comandos,
    )
    hilo = threading.Thread(target=suscribirse_a_comandos, args=(app,), daemon=True)
    hilo.start()


def create_app(configuracion=None):
    from gestion_trabajos.api import JsonEncoder
    from gestion_trabajos.config.db import db

    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(name)s | %(message)s',
    )

    app = Flask(__name__, instance_relative_config=True)
    app.json = JsonEncoder(app)
    app.secret_key = os.getenv('SECRET_KEY', 'dev')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URI',
        'postgresql+psycopg2://hogaralpes:hogaralpes@localhost:5432/gestion_trabajos',
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = (configuracion or {}).get('TESTING', False)

    db.init_app(app)

    importar_modelos_alchemy()
    registrar_handlers()
    registrar_comandos_y_queries()

    with app.app_context():
        from gestion_trabajos.modulos.trabajos.infraestructura.dto import (
            Base as BaseTrabajos,
        )
        from gestion_trabajos.modulos.operaciones.infraestructura.dto import (
            Base as BaseOperaciones,
        )
        BaseTrabajos.metadata.create_all(db.engine)
        BaseOperaciones.metadata.create_all(db.engine)

    from gestion_trabajos.api.trabajos import bp as bp_trabajos
    app.register_blueprint(bp_trabajos)

    @app.route('/health')
    def health():
        return jsonify({'status': 'up', 'service': 'gestion-trabajos'})

    if os.getenv('CONSUMIR_COMANDOS', 'false').lower() == 'true':
        comenzar_consumidor(app)

    return app
