"""US2, T032 — liberar una reserva es idempotente: un `DELETE` sobre una fila
que ya no existe (reentrega del comando) es un no-op, tanto a nivel del
repositorio de reservas como del comando de aplicación completo (FR-016).
"""
from datetime import date, timedelta

import pytest

from emparejamiento import crear_app
from emparejamiento.modulos.emparejamiento.aplicacion.comandos.actualizar_proveedor_candidato import (
    ActualizarProveedorCandidato,
)
from emparejamiento.modulos.emparejamiento.aplicacion.comandos.emparejar_trabajo import (
    EmparejarTrabajo,
)
from emparejamiento.modulos.emparejamiento.aplicacion.comandos.liberar_reserva import (
    LiberarReserva,
)
from emparejamiento.modulos.emparejamiento.aplicacion.queries.obtener_emparejamiento import (
    ObtenerEmparejamiento,
)
from emparejamiento.seedwork.aplicacion.comandos import ejecutar_comando
from emparejamiento.seedwork.aplicacion.queries import ejecutar_query

MANANA = (date.today() + timedelta(days=1)).isoformat()
TRABAJO_ID = '11111111-1111-1111-1111-111111111111'


@pytest.fixture
def app():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app


def _reservar():
    ejecutar_comando(ActualizarProveedorCandidato(
        proveedor_id='p1', pais='CO', ciudad='Bogota', categorias=['PLOMERIA'],
        nivel='ORO', estado='ACREDITADA', vigente_hasta=MANANA, version=1,
    ))
    ejecutar_comando(EmparejarTrabajo(
        trabajo_id=TRABAJO_ID, region='andina', categoria='PLOMERIA', pais='CO', ciudad='Bogota',
    ))


def test_liberar_una_reserva_existente_la_borra(app):
    _reservar()

    ejecutar_comando(LiberarReserva(trabajo_id=TRABAJO_ID, motivo='VIGENCIA_RECHAZADA'))

    from emparejamiento.modulos.emparejamiento.infraestructura.repositorios import (
        RepositorioEmparejamientosPostgres,
    )
    emparejamiento = RepositorioEmparejamientosPostgres().obtener_por_trabajo(TRABAJO_ID)
    assert emparejamiento.proveedor_reservado is None

    # El proveedor vuelve a estar disponible para un trabajo compatible nuevo.
    ejecutar_comando(EmparejarTrabajo(
        trabajo_id='22222222-2222-2222-2222-222222222222', region='andina',
        categoria='PLOMERIA', pais='CO', ciudad='Bogota',
    ))
    resultado = ejecutar_query(
        ObtenerEmparejamiento(trabajo_id='22222222-2222-2222-2222-222222222222')
    ).resultado
    assert resultado['candidatos'] == ['p1']


def test_liberar_dos_veces_la_misma_reserva_es_un_no_op(app):
    """Reentrega del mismo comando (al-menos-una-vez, Principio V): la segunda
    llamada no debe fallar ni volver a publicar `candidatos-liberados`."""
    _reservar()

    ejecutar_comando(LiberarReserva(trabajo_id=TRABAJO_ID, motivo='VIGENCIA_RECHAZADA'))
    ejecutar_comando(LiberarReserva(trabajo_id=TRABAJO_ID, motivo='VIGENCIA_RECHAZADA'))  # no-op


def test_liberar_una_reserva_que_nunca_existio_es_un_no_op(app):
    """Caso `SIN_CANDIDATOS`: nunca hubo reserva que liberar."""
    ejecutar_comando(LiberarReserva(trabajo_id='33333333-3333-3333-3333-333333333333', motivo='SIN_CANDIDATOS'))
