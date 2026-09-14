"""GT-4 (creación idempotente) y GT-6/MOD-1 (adaptador en memoria).

Corre con `ADAPTADOR_TRABAJOS=memoria` — el mismo adaptador que sostiene
`escenarios/mod-1.sh` — y `DATABASE_URI=sqlite:///:memory:` (la Unidad de
Trabajo sigue necesitando una sesión de SQLAlchemy para `commit()`/
`rollback()`, aunque el repositorio de Trabajo no la use para nada: sostiene
las tablas de `operaciones`, que sigue viva hasta GT-5).

No depende de PostgreSQL ni de un broker: es la prueba de la capa de
aplicación que MOD-1 dice que debía existir y no existía.
"""
import os

os.environ.setdefault('DATABASE_URI', 'sqlite:///:memory:')
os.environ['ADAPTADOR_TRABAJOS'] = 'memoria'

import pytest  # noqa: E402

from gestion_trabajos import crear_app  # noqa: E402
from gestion_trabajos.modulos.trabajos.aplicacion.comandos.crear_trabajo import (  # noqa: E402
    CrearTrabajo,
)
from gestion_trabajos.modulos.trabajos.infraestructura.repositorios_memoria import (  # noqa: E402
    RepositorioTrabajosMemoria,
)
from gestion_trabajos.seedwork.aplicacion.comandos import ejecutar_comando  # noqa: E402
from gestion_trabajos.seedwork.aplicacion.queries import ejecutar_query  # noqa: E402
from gestion_trabajos.modulos.trabajos.aplicacion.queries.obtener_trabajo import (  # noqa: E402
    ObtenerTrabajo,
)


@pytest.fixture
def app():
    RepositorioTrabajosMemoria.limpiar()
    aplicacion = crear_app({'TESTING': True})
    with aplicacion.app_context():
        yield aplicacion
    RepositorioTrabajosMemoria.limpiar()


def _comando(trabajo_id=''):
    return CrearTrabajo(
        trabajo_id=trabajo_id, canal='MARKETPLACE', partner_id='p1',
        referencia_externa='ref-1', categoria='PLOMERIA', urgencia='NORMAL',
        pais='CO', ciudad='Bogota', direccion='Cra 7', descripcion='fuga',
    )


def test_crear_trabajo_con_adaptador_en_memoria(app):
    id_ = ejecutar_comando(_comando())
    trabajo = ejecutar_query(ObtenerTrabajo(id=id_)).resultado
    assert trabajo is not None
    assert trabajo.categoria == 'PLOMERIA'


def test_crear_trabajo_sin_trabajo_id_crea_uno_nuevo_cada_vez(app):
    """Sin trabajo_id no hay con qué deduplicar (comportamiento previo, HTTP
    sin la extensión de GT-4): dos POST son dos trabajos."""
    id_1 = ejecutar_comando(_comando())
    id_2 = ejecutar_comando(_comando())
    assert id_1 != id_2


def test_crear_trabajo_con_el_mismo_trabajo_id_es_idempotente(app):
    """GT-4 / CA-E1: el mismo comando dos veces crea UN trabajo."""
    trabajo_id = '11111111-1111-1111-1111-111111111111'

    primero = ejecutar_comando(_comando(trabajo_id))
    segundo = ejecutar_comando(_comando(trabajo_id))  # reintento del productor

    assert primero == segundo == trabajo_id
    assert len(RepositorioTrabajosMemoria._ALMACEN) == 1
