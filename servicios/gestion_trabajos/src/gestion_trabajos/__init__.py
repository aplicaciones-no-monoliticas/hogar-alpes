"""Servicio Gestión de Trabajos — Hogar de los Alpes.

Application factory. El orden de importación importa: los módulos de handlers se
importan explícitamente para que sus `dispatcher.connect` queden registrados
antes de atender el primer request.

El consumidor **ya no arranca aquí**: corre como proceso propio
(`python -m gestion_trabajos.consumidor`). Ver `consumidor.py`.
"""
import logging
import os

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


def _crear_tablas(bases, engine):
    """`create_all` no es atómico frente a la carrera real de este servicio:
    `api` y `consumidor` son DOS procesos separados (§1 del plan técnico) y los
    dos llaman `crear_app()` al arrancar. Contra una base recién creada, ambos
    ven "la tabla no existe" al mismo tiempo y los dos emiten `CREATE TABLE`;
    PostgreSQL deja pasar solo al primero y el segundo revienta con
    `IntegrityError` sobre el catálogo (`pg_type_typname_nsp_index`), no con el
    "ya existe" que uno esperaría. Se reintenta: a la vuelta siguiente,
    `create_all` ve las tablas del que ganó la carrera y no hace nada.

    Misma solución que Operaciones, Acreditación y Emparejamiento: es el costo
    de `TO-7`, el mismo arreglo repetido en cada copia.
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


def crear_app(configuracion=None):
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
        _crear_tablas([BaseTrabajos, BaseOperaciones], db.engine)

    from gestion_trabajos.api.trabajos import bp as bp_trabajos
    app.register_blueprint(bp_trabajos)

    @app.route('/health')
    def health():
        return jsonify({
            'status': 'up',
            'service': 'gestion-trabajos',
            'modo': os.getenv('MODO', 'api'),
        })

    return app


# `flask run` y las pruebas siguen encontrando el nombre de siempre.
create_app = crear_app
