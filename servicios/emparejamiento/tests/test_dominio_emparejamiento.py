"""Pruebas del modelo de dominio. Sin base de datos y sin broker."""
import uuid

import pytest

from emparejamiento.modulos.emparejamiento.dominio.entidades import Emparejamiento
from emparejamiento.modulos.emparejamiento.dominio.eventos import (
    CandidatosIdentificados,
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
