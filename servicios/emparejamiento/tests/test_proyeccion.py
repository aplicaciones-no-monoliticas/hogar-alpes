"""EMP-2 · EMP-5 — la proyección de proveedores: upsert por versión, tolerante
al desorden, y la regla de vigencia (solo `ACREDITADA` y no vencida).
"""
from datetime import date, timedelta

import pytest

from emparejamiento import crear_app
from emparejamiento.modulos.emparejamiento.infraestructura.repositorios import (
    RepositorioProveedoresCandidatosPostgres,
)


@pytest.fixture
def app():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app


MANANA = (date.today() + timedelta(days=1)).isoformat()
AYER = (date.today() - timedelta(days=1)).isoformat()


def test_upsert_crea_el_registro_si_no_existe(app):
    from emparejamiento.config.db import db

    repo = RepositorioProveedoresCandidatosPostgres()
    repo.upsert('p1', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'ACREDITADA', MANANA, version=1)
    db.session.commit()

    encontrados = repo.buscar('PLOMERIA', 'CO', 'Bogota')
    assert [c['proveedor_id'] for c in encontrados] == ['p1']


def test_upsert_con_version_mayor_actualiza(app):
    from emparejamiento.config.db import db

    repo = RepositorioProveedoresCandidatosPostgres()
    repo.upsert('p1', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'SOLICITADA', '', version=1)
    db.session.commit()

    repo.upsert('p1', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'ACREDITADA', MANANA, version=2)
    db.session.commit()

    encontrados = repo.buscar('PLOMERIA', 'CO', 'Bogota')
    assert len(encontrados) == 1
    assert encontrados[0]['vigente_hasta'] == MANANA


def test_upsert_con_version_menor_o_igual_se_ignora(app):
    """Tolerante al desorden: un evento viejo llegado tarde no pisa el más
    nuevo que ya se aplicó (§5.3 de la especificación)."""
    from emparejamiento.config.db import db

    repo = RepositorioProveedoresCandidatosPostgres()
    repo.upsert('p1', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'ACREDITADA', MANANA, version=5)
    db.session.commit()

    repo.upsert('p1', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'REVOCADA', '', version=3)
    db.session.commit()
    repo.upsert('p1', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'REVOCADA', '', version=5)
    db.session.commit()

    encontrados = repo.buscar('PLOMERIA', 'CO', 'Bogota')
    assert encontrados[0]['vigente_hasta'] == MANANA  # sigue vigente: no lo pisó la 3 ni la 5


def test_buscar_excluye_no_acreditados(app):
    from emparejamiento.config.db import db

    repo = RepositorioProveedoresCandidatosPostgres()
    repo.upsert('p1', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'SOLICITADA', '', version=1)
    repo.upsert('p2', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'REVOCADA', MANANA, version=1)
    db.session.commit()

    assert repo.buscar('PLOMERIA', 'CO', 'Bogota') == []


def test_buscar_excluye_vencidos(app):
    from emparejamiento.config.db import db

    repo = RepositorioProveedoresCandidatosPostgres()
    repo.upsert('p1', 'PLOMERIA', 'CO', 'Bogota', 'ORO', 'ACREDITADA', AYER, version=1)
    db.session.commit()

    assert repo.buscar('PLOMERIA', 'CO', 'Bogota') == []


def test_una_acreditacion_certifica_varias_categorias_por_separado(app):
    """Es lo que resuelve `ActualizarProveedorCandidato`: una fila por
    (proveedor, categoría), no una por proveedor."""
    from emparejamiento.config.db import db

    repo = RepositorioProveedoresCandidatosPostgres()
    for categoria in ('PLOMERIA', 'GAS'):
        repo.upsert('p1', categoria, 'CO', 'Bogota', 'ORO', 'ACREDITADA', MANANA, version=1)
    db.session.commit()

    assert len(repo.buscar('PLOMERIA', 'CO', 'Bogota')) == 1
    assert len(repo.buscar('GAS', 'CO', 'Bogota')) == 1
