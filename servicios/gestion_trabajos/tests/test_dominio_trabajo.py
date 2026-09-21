"""Pruebas del modelo de dominio. Sin base de datos y sin broker: si estas
pruebas necesitaran infraestructura, el aislamiento del dominio estaría roto.
"""
import pytest

from gestion_trabajos.modulos.trabajos.dominio.entidades import SubTrabajo, Trabajo
from gestion_trabajos.modulos.trabajos.dominio.eventos import (
    EstadoTrabajoCambiado,
    TrabajoCreado,
)
from gestion_trabajos.modulos.trabajos.dominio.objetos_valor import (
    Canal,
    Categoria,
    Estado,
    EstadoTrabajo,
    Solicitante,
    Ubicacion,
    Urgencia,
)
from gestion_trabajos.seedwork.dominio.excepciones import ReglaNegocioExcepcion

CATEGORIAS = ['PLOMERIA', 'SINIESTRO_GRANIZO']
URGENCIAS = ['CRITICA', 'NORMAL']


def _trabajo(categoria='PLOMERIA', urgencia='NORMAL', pais='CO'):
    return Trabajo(
        solicitante=Solicitante(canal=Canal.B2B2C, partner_id='seguros-alpes'),
        categoria=Categoria(codigo=categoria),
        urgencia=Urgencia(nivel=urgencia),
        ubicacion=Ubicacion(pais=pais, ciudad='Bogota', direccion='Cra 7 # 71-21'),
        descripcion='Fuga en el baño',
    )


def test_crear_emite_evento_de_dominio():
    trabajo = _trabajo()
    trabajo.crear(CATEGORIAS, URGENCIAS)

    assert trabajo.estado == EstadoTrabajo(Estado.CREADO)
    assert len(trabajo.eventos) == 1
    assert isinstance(trabajo.eventos[0], TrabajoCreado)
    assert trabajo.eventos[0].trabajo_id == trabajo.id


def test_categoria_fuera_de_la_region_se_rechaza():
    trabajo = _trabajo(categoria='SISMO')
    with pytest.raises(ReglaNegocioExcepcion):
        trabajo.crear(CATEGORIAS, URGENCIAS)


def test_ubicacion_incompleta_se_rechaza():
    trabajo = _trabajo()
    trabajo.ubicacion = Ubicacion(pais='CO', ciudad='', direccion='')
    with pytest.raises(ReglaNegocioExcepcion):
        trabajo.crear(CATEGORIAS, URGENCIAS)


def test_transicion_valida_emite_evento():
    trabajo = _trabajo()
    trabajo.crear(CATEGORIAS, URGENCIAS)
    trabajo.cambiar_estado(Estado.EMPAREJANDO)

    assert trabajo.estado.valor == Estado.EMPAREJANDO
    evento = trabajo.eventos[-1]
    assert isinstance(evento, EstadoTrabajoCambiado)
    assert (evento.estado_anterior, evento.estado_nuevo) == ('CREADO', 'EMPAREJANDO')


def test_transicion_invalida_rompe_la_regla():
    trabajo = _trabajo()
    trabajo.crear(CATEGORIAS, URGENCIAS)
    with pytest.raises(ReglaNegocioExcepcion):
        trabajo.cambiar_estado(Estado.COMPLETADO)


def test_estado_nuevo_del_escenario_3_esta_en_el_ciclo_de_vida():
    """EN_VERIFICACION se agregó tocando solo el objeto valor."""
    assert EstadoTrabajo(Estado.EN_EJECUCION).puede_transicionar_a(Estado.EN_VERIFICACION)
    assert EstadoTrabajo(Estado.EN_VERIFICACION).puede_transicionar_a(Estado.COMPLETADO)


def test_sub_trabajo_vive_dentro_del_agregado():
    trabajo = _trabajo()
    trabajo.crear(CATEGORIAS, URGENCIAS)
    trabajo.agregar_sub_trabajo(
        SubTrabajo(descripcion='Cambiar sifón', categoria=Categoria(codigo='PLOMERIA'))
    )
    assert len(trabajo.sub_trabajos) == 1
    assert trabajo.eventos[-1].trabajo_id == trabajo.id


# ------------------------------------------------------- saga (Entrega 5, T015/T033)

def test_proveedor_id_es_none_hasta_que_se_asigna():
    trabajo = _trabajo()
    assert trabajo.proveedor_id is None


def test_creado_a_emparejando_es_una_transicion_valida():
    """D2 de research.md: la transición ya está declarada en TRANSICIONES; la
    saga solo necesitaba quien la disparara."""
    trabajo = _trabajo()
    trabajo.crear(CATEGORIAS, URGENCIAS)
    trabajo.cambiar_estado(Estado.EMPAREJANDO)

    assert trabajo.estado.valor == Estado.EMPAREJANDO
    assert trabajo.eventos[-1].estado_nuevo == 'EMPAREJANDO'


def test_asignar_proveedor_id_junto_con_la_transicion_a_asignado():
    trabajo = _trabajo()
    trabajo.crear(CATEGORIAS, URGENCIAS)
    trabajo.cambiar_estado(Estado.EMPAREJANDO)

    trabajo.proveedor_id = 'proveedor-1'
    trabajo.cambiar_estado(Estado.ASIGNADO)

    assert trabajo.estado.valor == Estado.ASIGNADO
    assert trabajo.proveedor_id == 'proveedor-1'


@pytest.mark.parametrize('motivo', ['sin_candidatos', 'vigencia_rechazada', 'asignacion_fallida'])
def test_emparejando_a_cancelado_es_valida_para_los_tres_motivos_de_falla(motivo):
    """US2, T033: los tres puntos de falla de la saga (`SIN_CANDIDATOS`,
    `VIGENCIA`, `ASIGNACION`) terminan en la misma transición de dominio —
    solo cambia quién la dispara, no la regla."""
    trabajo = _trabajo()
    trabajo.crear(CATEGORIAS, URGENCIAS)
    trabajo.cambiar_estado(Estado.EMPAREJANDO)

    trabajo.cambiar_estado(Estado.CANCELADO)

    assert trabajo.estado.valor == Estado.CANCELADO
    assert trabajo.proveedor_id is None
    assert (trabajo.eventos[-1].estado_anterior, trabajo.eventos[-1].estado_nuevo) == (
        'EMPAREJANDO', 'CANCELADO',
    )


def test_simular_fallo_viaja_en_el_evento_sin_tocar_el_contrato():
    """D3 de research.md: la marca de simulación es un dato del evento de
    dominio, nunca un campo del esquema Avro (eso lo decide el mapeador)."""
    trabajo = _trabajo()
    trabajo.crear(CATEGORIAS, URGENCIAS, simular_fallo='SIN_CANDIDATOS')

    assert trabajo.eventos[0].simular_fallo == 'SIN_CANDIDATOS'
