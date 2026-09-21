"""Pruebas del modelo de dominio. Sin base de datos y sin broker."""
import uuid

import pytest

from emparejamiento.modulos.emparejamiento.dominio.entidades import Emparejamiento
from emparejamiento.modulos.emparejamiento.dominio.eventos import (
    CandidatosIdentificados,
    CandidatosLiberados,
    ProveedorPropuesto,
    SinCandidatos,
)
from emparejamiento.modulos.emparejamiento.dominio.objetos_valor import (
    Candidato,
    CriterioBusqueda,
)
from emparejamiento.seedwork.dominio.excepciones import ReglaNegocioExcepcion


def _emparejamiento():
    trabajo_id = uuid.uuid4()
    return Emparejamiento(id=trabajo_id, trabajo_id=trabajo_id, region='andina')


def test_emparejar_con_candidatos_emite_candidatos_identificados():
    emparejamiento = _emparejamiento()
    criterio = CriterioBusqueda(categoria='PLOMERIA', pais='CO', ciudad='Bogota')
    candidatos = [Candidato(proveedor_id='p1', nivel='ORO'), Candidato(proveedor_id='p2', nivel='PLATA')]

    emparejamiento.emparejar(criterio, candidatos)

    assert emparejamiento.candidatos == candidatos
    assert len(emparejamiento.eventos) == 1
    evento = emparejamiento.eventos[0]
    assert isinstance(evento, CandidatosIdentificados)
    assert evento.proveedores_id == ['p1', 'p2']
    assert evento.trabajo_id == emparejamiento.trabajo_id


def test_emparejar_sin_candidatos_emite_sin_candidatos():
    emparejamiento = _emparejamiento()
    criterio = CriterioBusqueda(categoria='PLOMERIA', pais='CO', ciudad='Bogota')

    emparejamiento.emparejar(criterio, [])

    assert emparejamiento.candidatos == []
    assert isinstance(emparejamiento.eventos[0], SinCandidatos)


def test_criterio_incompleto_rompe_la_regla():
    emparejamiento = _emparejamiento()
    criterio = CriterioBusqueda(categoria='', pais='CO', ciudad='Bogota')

    with pytest.raises(ReglaNegocioExcepcion):
        emparejamiento.emparejar(criterio, [])


# ---------------------------------------------------------------- saga (T016)

def test_proponer_proveedor_reservado_emite_proveedor_propuesto():
    emparejamiento = _emparejamiento()
    criterio = CriterioBusqueda(categoria='PLOMERIA', pais='CO', ciudad='Bogota')
    candidatos = [Candidato(proveedor_id='p1', nivel='ORO'), Candidato(proveedor_id='p2', nivel='PLATA')]
    emparejamiento.emparejar(criterio, candidatos)

    emparejamiento.proponer_proveedor('p1')

    assert emparejamiento.proveedor_reservado == 'p1'
    evento = emparejamiento.eventos[-1]
    assert isinstance(evento, ProveedorPropuesto)
    assert evento.proveedor_id == 'p1'
    assert evento.candidatos == ['p1', 'p2']


def test_agotar_candidatos_equivale_a_sin_candidatos():
    """D1 de research.md: la lista completa se probó y ninguno pudo
    reservarse — equivalente a sin candidatos para la saga."""
    emparejamiento = _emparejamiento()
    criterio = CriterioBusqueda(categoria='PLOMERIA', pais='CO', ciudad='Bogota')
    emparejamiento.emparejar(criterio, [Candidato(proveedor_id='p1', nivel='ORO')])

    emparejamiento.agotar_candidatos()

    assert emparejamiento.proveedor_reservado is None
    assert isinstance(emparejamiento.eventos[-1], SinCandidatos)


def test_liberar_reserva_limpia_el_proveedor_y_emite_candidatos_liberados():
    emparejamiento = _emparejamiento()
    criterio = CriterioBusqueda(categoria='PLOMERIA', pais='CO', ciudad='Bogota')
    emparejamiento.emparejar(criterio, [Candidato(proveedor_id='p1', nivel='ORO')])
    emparejamiento.proponer_proveedor('p1')

    emparejamiento.liberar_reserva('VIGENCIA_RECHAZADA')

    assert emparejamiento.proveedor_reservado is None
    evento = emparejamiento.eventos[-1]
    assert isinstance(evento, CandidatosLiberados)
    assert evento.proveedor_id == 'p1'
    assert evento.motivo == 'VIGENCIA_RECHAZADA'
