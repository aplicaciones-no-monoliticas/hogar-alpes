"""T042 — la tabla de derivación de estado (D9 de research.md): qué paso
observado produce qué estado de la transacción.

T043 — un `mensaje_id` duplicado (reentrega del broker) no duplica un paso en
la línea de tiempo (CA-1.14, FR-016).
"""
from datetime import datetime

from saga_log.modulos.sagas.infraestructura.repositorios import RepositorioSagas

AHORA = datetime(2026, 9, 20, 10, 0, 0)
TRABAJO_ID = 't-1'


def _registrar(repo, mensaje_id, servicio, tipo, estado_mensaje='', trabajo_id=TRABAJO_ID):
    repo.registrar_paso(
        mensaje_id=mensaje_id, trabajo_id=trabajo_id, correlation_id='cid-1',
        servicio=servicio, tipo=tipo, ocurrido_en=AHORA, estado_mensaje=estado_mensaje,
    )


# --------------------------------------------------------- D9: derivación de estado

def test_trabajo_creado_deja_la_transaccion_en_curso(app):
    repo = RepositorioSagas()
    _registrar(repo, 'm1', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')

    transaccion = repo.obtener_transaccion(TRABAJO_ID)
    assert transaccion.estado == 'EN_CURSO'
    assert transaccion.terminada_en is None


def test_estado_cambiado_a_asignado_completa_la_transaccion(app):
    repo = RepositorioSagas()
    _registrar(repo, 'm1', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')
    _registrar(repo, 'm2', 'gestion-trabajos', 'hogaralpes.trabajo.estado-cambiado.v1',
               estado_mensaje='ASIGNADO')

    transaccion = repo.obtener_transaccion(TRABAJO_ID)
    assert transaccion.estado == 'COMPLETADA'
    assert transaccion.terminada_en == AHORA


def test_sin_candidatos_compensa_directo_sin_pasar_por_compensando(app):
    repo = RepositorioSagas()
    _registrar(repo, 'm1', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')
    _registrar(repo, 'm2', 'emparejamiento', 'hogaralpes.emparejamiento.sin-candidatos.v1')

    transaccion = repo.obtener_transaccion(TRABAJO_ID)
    assert transaccion.estado == 'COMPENSADA'
    assert transaccion.terminada_en == AHORA


def test_vigencia_rechazada_dispara_compensando(app):
    repo = RepositorioSagas()
    _registrar(repo, 'm1', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')
    _registrar(repo, 'm2', 'acreditacion', 'hogaralpes.acreditacion.vigencia-rechazada.v1')

    assert repo.obtener_transaccion(TRABAJO_ID).estado == 'COMPENSANDO'


def test_candidatos_liberados_dispara_compensando(app):
    repo = RepositorioSagas()
    _registrar(repo, 'm1', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')
    _registrar(repo, 'm2', 'emparejamiento', 'hogaralpes.emparejamiento.candidatos-liberados.v1')

    assert repo.obtener_transaccion(TRABAJO_ID).estado == 'COMPENSANDO'


def test_estado_cambiado_a_cancelado_compensa_la_transaccion(app):
    repo = RepositorioSagas()
    _registrar(repo, 'm1', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')
    _registrar(repo, 'm2', 'acreditacion', 'hogaralpes.acreditacion.vigencia-rechazada.v1')
    _registrar(repo, 'm3', 'gestion-trabajos', 'hogaralpes.trabajo.estado-cambiado.v1',
               estado_mensaje='CANCELADO')

    transaccion = repo.obtener_transaccion(TRABAJO_ID)
    assert transaccion.estado == 'COMPENSADA'
    assert transaccion.terminada_en == AHORA


def test_un_estado_final_no_se_mueve_por_un_paso_tardio(app):
    """Un paso reentregado o fuera de orden después de un estado final no debe
    reabrir la transacción."""
    repo = RepositorioSagas()
    _registrar(repo, 'm1', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')
    _registrar(repo, 'm2', 'gestion-trabajos', 'hogaralpes.trabajo.estado-cambiado.v1',
               estado_mensaje='ASIGNADO')

    # Una copia rezagada de `candidatos-identificados`, sin efecto sobre el estado.
    _registrar(repo, 'm3', 'emparejamiento', 'hogaralpes.emparejamiento.candidatos-identificados.v1')

    assert repo.obtener_transaccion(TRABAJO_ID).estado == 'COMPLETADA'


# ------------------------------------------------------------------- T043: dedupe

def test_un_mensaje_id_duplicado_no_duplica_el_paso(app):
    repo = RepositorioSagas()
    _registrar(repo, 'm-repetido', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')
    _registrar(repo, 'm-repetido', 'gestion-trabajos', 'hogaralpes.trabajo.creado.v1')  # reentrega

    pasos = repo.obtener_pasos(TRABAJO_ID)
    assert len(pasos) == 1


def test_un_mensaje_sin_trabajo_id_no_se_registra(app):
    """D8: `evt-acreditacion` sin trabajo_id (la `actualizada` que no
    pertenece a ninguna saga) no debe crear una transacción huérfana."""
    repo = RepositorioSagas()
    _registrar(repo, 'm1', 'acreditacion', 'hogaralpes.acreditacion.vigencia-confirmada.v1',
               trabajo_id='')

    assert repo.obtener_transaccion('') is None
