"""Fábrica de la aplicación.

Cada servicio extiende los tres puntos marcados abajo: sus modelos, sus
handlers y sus rutas. El resto —base de datos, codificación JSON, salud— es
común y no debería tocarse.
"""
import logging
import os

from flask import Flask


def _registrar_modelos():
    """PUNTO DE EXTENSIÓN 1 — importar los modelos de persistencia del servicio,
    para que SQLAlchemy los conozca antes de crear las tablas. Devuelve la lista
    de `Base` cuyas tablas hay que crear."""
    return []


def _registrar_handlers():
    """PUNTO DE EXTENSIÓN 2 — importar los módulos de handlers, comandos y
    consultas, de modo que sus suscripciones y sus `singledispatch` queden
    registrados antes de atender la primera petición."""


def _registrar_rutas(app):
    """PUNTO DE EXTENSIÓN 3 — registrar los blueprints del servicio."""


def crear_app(configuracion: dict | None = None) -> Flask:
    from .api import JsonEncoder
    from .api.salud import bp as bp_salud
    from .config.db import db

    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(name)s | %(message)s',
    )

    app = Flask(__name__, instance_relative_config=True)
    app.json = JsonEncoder(app)
    app.secret_key = os.getenv('SECRET_KEY', 'dev')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI', 'sqlite:///:memory:')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = (configuracion or {}).get('TESTING', False)

    db.init_app(app)

    bases = _registrar_modelos()
    _registrar_handlers()

    with app.app_context():
        for base in bases:
            base.metadata.create_all(db.engine)

    app.register_blueprint(bp_salud)
    _registrar_rutas(app)

    return app
