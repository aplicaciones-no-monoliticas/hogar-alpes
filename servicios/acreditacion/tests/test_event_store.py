"""ACR-2 · ACR-5 — event store: append, rehidratación, concurrencia optimista.

Usa SQLite en memoria (`crear_app()` sin `DATABASE_URI`, igual que la
plantilla). No hace falta PostgreSQL para probar esta capa: el motor es
intercambiable porque el repositorio solo habla con SQLAlchemy.
"""
import pytest

from acreditacion import crear_app
from acreditacion.modulos.acreditacion.dominio.entidades import Acreditacion
from acreditacion.modulos.acreditacion.dominio.excepciones import (
    ConflictoDeConcurrenciaExcepcion,
)
from acreditacion.modulos.acreditacion.infraestructura.repositorios import (
    RepositorioAcreditacionesEventSourcing,
)


@pytest.fixture
def app():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app


def _nueva(repo):
    acreditacion = Acreditacion.solicitar(
        proveedor_id='prov-1', pais='CO', ciudad='Bogota',
        categorias=['PLOMERIA', 'GAS'], nivel='ORO', vigencia_meses=12,
    )
    repo.agregar(acreditacion)
    from acreditacion.config.db import db
    db.session.commit()
    return acreditacion


def test_agregar_y_reconstruir_coincide_con_el_estado_original(app):
    """Igual que un handler de comando real: `aprobar` se ejecuta sobre una
    instancia recién cargada del repositorio, no sobre la que quedó en memoria
    de la solicitud — `acreditacion.eventos` solo debe traer lo pendiente de
    ESTE comando; lo ya persistido lo limpia `obtener_por_id`."""
    from acreditacion.config.db import db

    repo = RepositorioAcreditacionesEventSourcing()
    acreditacion_id = _nueva(repo).id

    acreditacion = repo.obtener_por_id(acreditacion_id)
    acreditacion.aprobar(motivo='ok')
    repo.agregar(acreditacion)
    db.session.commit()

    reconstruida = repo.obtener_por_id(acreditacion.id)

    assert reconstruida is not None
    assert reconstruida.estado == acreditacion.estado
    assert reconstruida.vigente_hasta == acreditacion.vigente_hasta
    # Contra un LITERAL, no contra `acreditacion.vigente_hasta` (que en este
    # caso YA viene del mismo cálculo que se está verificando): comparar un
    # valor contra sí mismo pasa aunque el cálculo esté mal — es la misma
    # trampa que documenta CON-1 en `docs/decisiones.md`. Se descubrió así:
    # `aprobar()` sobre un agregado reconstruido daba `vigente_hasta = hoy`
    # porque `vigencia_meses` no viajaba en el evento — regresión cubierta
    # aquí.
    from datetime import date, timedelta
    assert reconstruida.vigente_hasta == (date.today() + timedelta(days=360)).isoformat()
    assert reconstruida.version == 2
    assert reconstruida.categorias == ['PLOMERIA', 'GAS']
    # Reproducir el historial no deja eventos pendientes de publicar de nuevo.
    assert reconstruida.eventos == []


def test_obtener_por_id_inexistente_devuelve_none(app):
    repo = RepositorioAcreditacionesEventSourcing()
    assert repo.obtener_por_id('00000000-0000-0000-0000-000000000000') is None


def test_dos_escrituras_con_la_misma_version_la_segunda_falla(app):
    """Simula dos comandos concurrentes que cargaron el agregado en la MISMA
    versión y ambos intentan aprobar: el segundo debe chocar con
    `UNIQUE(agregado_id, version)`, no silenciarse ni sobrescribir al primero.
    """
    from acreditacion.config.db import db

    repo = RepositorioAcreditacionesEventSourcing()
    original = _nueva(repo)

    copia_a = repo.obtener_por_id(original.id)
    copia_b = repo.obtener_por_id(original.id)

    copia_a.aprobar(motivo='primer aprobador')
    repo.agregar(copia_a)
    db.session.commit()

    copia_b.aprobar(motivo='segundo aprobador, llegó tarde')
    with pytest.raises(ConflictoDeConcurrenciaExcepcion):
        repo.agregar(copia_b)


def test_historial_devuelve_los_eventos_en_orden(app):
    from acreditacion.config.db import db

    repo = RepositorioAcreditacionesEventSourcing()
    acreditacion_id = _nueva(repo).id

    acreditacion = repo.obtener_por_id(acreditacion_id)
    acreditacion.aprobar()
    repo.agregar(acreditacion)
    db.session.commit()

    acreditacion = repo.obtener_por_id(acreditacion_id)
    acreditacion.revocar(motivo='denuncia')
    repo.agregar(acreditacion)
    db.session.commit()

    historial = repo.historial(acreditacion.id)

    assert [h['tipo'] for h in historial] == [
        'AcreditacionSolicitada', 'AcreditacionAprobada', 'AcreditacionRevocada',
    ]
    assert [h['version'] for h in historial] == [1, 2, 3]


# --------------------------------------------- saga (Entrega 5, D4/T017/T027)

def test_agregar_actualiza_vigencia_por_proveedor_en_la_misma_transaccion(app):
    from acreditacion.config.db import db
    from acreditacion.modulos.acreditacion.infraestructura.repositorios import (
        RepositorioVigenciaPorProveedorPostgres,
    )

    repo = RepositorioAcreditacionesEventSourcing()
    acreditacion = _nueva(repo)  # SOLICITADA, version=1
    repo_vigencia = RepositorioVigenciaPorProveedorPostgres()

    for categoria in ('PLOMERIA', 'GAS'):
        vigencia = repo_vigencia.consultar('prov-1', categoria)
        assert vigencia == {'estado': 'SOLICITADA', 'vigente_hasta': '', 'version': 1}

    acreditacion = repo.obtener_por_id(acreditacion.id)
    acreditacion.aprobar()
    repo.agregar(acreditacion)
    db.session.commit()

    vigencia = repo_vigencia.consultar('prov-1', 'PLOMERIA')
    assert vigencia['estado'] == 'ACREDITADA'
    assert vigencia['version'] == 2


def test_vigencia_por_proveedor_es_tolerante_al_desorden(app):
    """D4: un evento viejo llegado tarde (version menor) no pisa uno más
    nuevo que ya se aplicó."""
    from acreditacion.modulos.acreditacion.infraestructura.repositorios import (
        RepositorioVigenciaPorProveedorPostgres,
    )

    repo = RepositorioVigenciaPorProveedorPostgres()
    repo.upsert('prov-2', 'PLOMERIA', estado='ACREDITADA', vigente_hasta='2027-01-01', version=5)

    repo.upsert('prov-2', 'PLOMERIA', estado='REVOCADA', vigente_hasta='2027-01-01', version=3)

    vigencia = repo.consultar('prov-2', 'PLOMERIA')
    assert vigencia == {'estado': 'ACREDITADA', 'vigente_hasta': '2027-01-01', 'version': 5}
