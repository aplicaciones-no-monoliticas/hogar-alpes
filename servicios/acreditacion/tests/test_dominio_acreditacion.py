"""Pruebas del modelo de dominio. Sin base de datos y sin broker: si estas
pruebas necesitaran infraestructura, el aislamiento del dominio estaría roto.
"""
import pytest

from acreditacion.modulos.acreditacion.dominio.entidades import Acreditacion
from acreditacion.modulos.acreditacion.dominio.eventos import (
    AcreditacionAprobada,
    AcreditacionRevocada,
    AcreditacionSolicitada,
)
from acreditacion.modulos.acreditacion.dominio.objetos_valor import Estado
from acreditacion.seedwork.dominio.excepciones import ReglaNegocioExcepcion


def _acreditacion(categorias=('PLOMERIA',)):
    return Acreditacion.solicitar(
        proveedor_id='prov-1', pais='CO', ciudad='Bogota',
        categorias=list(categorias), nivel='ORO', vigencia_meses=12,
    )


def test_solicitar_emite_evento_y_queda_en_solicitada():
    acreditacion = _acreditacion()

    assert acreditacion.estado.valor == Estado.SOLICITADA
    assert acreditacion.version == 1
    assert len(acreditacion.eventos) == 1
    assert isinstance(acreditacion.eventos[0], AcreditacionSolicitada)
    assert acreditacion.eventos[0].version == 1


def test_solicitar_sin_categorias_rompe_la_regla():
    with pytest.raises(ReglaNegocioExcepcion):
        _acreditacion(categorias=[])


def test_aprobar_desde_solicitada_transiciona_y_fija_vigencia():
    acreditacion = _acreditacion()
    acreditacion.aprobar(motivo='documentos verificados')

    assert acreditacion.estado.valor == Estado.ACREDITADA
    assert acreditacion.vigente_hasta
    assert acreditacion.version == 2
    assert isinstance(acreditacion.eventos[-1], AcreditacionAprobada)


def test_revocar_sin_estar_acreditada_rompe_la_regla():
    acreditacion = _acreditacion()
    with pytest.raises(ReglaNegocioExcepcion):
        acreditacion.revocar(motivo='denuncia')


def test_revocar_desde_acreditada_transiciona():
    acreditacion = _acreditacion()
    acreditacion.aprobar()
    acreditacion.revocar(motivo='denuncia')

    assert acreditacion.estado.valor == Estado.REVOCADA
    assert acreditacion.version == 3
    assert isinstance(acreditacion.eventos[-1], AcreditacionRevocada)


def test_aplicar_evento_reproduce_el_mismo_estado_que_registrarlo():
    """Es la garantía de la que depende la reconstrucción del repositorio:
    reproducir el log con `aplicar_evento` debe llegar al mismo estado que
    llegó el agregado original al emitir esos eventos."""
    original = _acreditacion()
    original.aprobar(motivo='ok')

    reconstruido = Acreditacion(id=original.id)
    for evento in original.eventos:
        reconstruido.aplicar_evento(evento)

    assert reconstruido.estado == original.estado
    assert reconstruido.vigente_hasta == original.vigente_hasta
    assert reconstruido.version == original.version
    assert reconstruido.categorias == original.categorias
