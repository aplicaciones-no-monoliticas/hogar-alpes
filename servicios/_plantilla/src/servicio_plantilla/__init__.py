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


def _crear_tablas(bases, engine):
    """`create_all` no es atómico frente a la carrera real de un servicio con
    dos procesos: `api` y `consumidor` llaman los dos a `crear_app()` al
    arrancar. Contra una base recién creada, ambos ven "la tabla no existe" al
    mismo tiempo y los dos emiten `CREATE TABLE`; PostgreSQL deja pasar solo al
    primero y el segundo revienta con `IntegrityError` sobre el catálogo
    (`pg_type_typname_nsp_index`), no con el "ya existe" que uno esperaría. Se
    reintenta: a la vuelta siguiente, `create_all` ve las tablas del que ganó la
    carrera y no hace nada.

    Sin esto, `docker compose up` desde volúmenes vacíos deja muerta, a cara o
    cruz, la API o el consumidor.
    """
    import time

    from sqlalchemy.exc import IntegrityError, OperationalError

    for intento in range(5):
        try:
            for base in bases:
                base.metadata.create_all(engine)
            return
        except (IntegrityError, OperationalError):
            if intento == 4:
                raise
            time.sleep(0.5 * (intento + 1))


def crear_app(configuracion: dict | None = None) -> Flask:
    from .api import JsonEncoder
    from .api.salud import bp as bp_salud
    from .config.db import db
    from .seedwork.infraestructura import correlacion

    correlacion.instalar_registro()
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(name)s | cid=%(correlation_id)s%(campos)s | %(message)s',
    )

    app = Flask(__name__, instance_relative_config=True)
    # Cada servicio nuevo declara aquí el argumento de ruta que lleva el id de su
    # negocio: `campos_ruta={'id': 'trabajo_id'}` (`saga_log` usará `trabajo_id`).
    correlacion.instalar_en_flask(app)
    app.json = JsonEncoder(app)
    app.secret_key = os.getenv('SECRET_KEY', 'dev')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI', 'sqlite:///:memory:')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = (configuracion or {}).get('TESTING', False)

    db.init_app(app)

    bases = _registrar_modelos()
    _registrar_handlers()

    with app.app_context():
        _crear_tablas(bases, db.engine)

    app.register_blueprint(bp_salud)
    _registrar_rutas(app)

    return app
