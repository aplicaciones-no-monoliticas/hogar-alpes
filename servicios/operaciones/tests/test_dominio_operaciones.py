"""OPS-1 — dominio puro, sin base de datos ni broker."""
from operaciones.modulos.operaciones.dominio.fabricas import FabricaSeguimientos
from operaciones.modulos.operaciones.dominio.objetos_valor import Prioridad


def test_fabrica_aplica_la_politica_sla_por_urgencia():
    seguimiento = FabricaSeguimientos().crear_objeto({
        'trabajo_id': 't1', 'pais': 'CO', 'canal': 'app',
        'categoria': 'PLOMERIA', 'estado': 'CREADO', 'urgencia': 'CRITICA',
    })
    assert seguimiento.ventana_sla.minutos == 60
    assert seguimiento.ventana_sla.prioridad == Prioridad.P1


def test_fabrica_usa_normal_si_la_urgencia_no_se_reconoce():
    seguimiento = FabricaSeguimientos().crear_objeto({
        'trabajo_id': 't2', 'pais': 'CO', 'canal': 'app',
        'categoria': 'PLOMERIA', 'estado': 'CREADO', 'urgencia': 'DESCONOCIDA',
    })
    assert seguimiento.ventana_sla.minutos == 1440


def test_abrir_agrega_el_evento_de_dominio():
    seguimiento = FabricaSeguimientos().crear_objeto({
        'trabajo_id': 't3', 'pais': 'CO', 'canal': 'app',
        'categoria': 'PLOMERIA', 'estado': 'CREADO', 'urgencia': 'ALTA',
    })
    assert len(seguimiento.eventos) == 1
    assert type(seguimiento.eventos[0]).__name__ == 'SeguimientoAbierto'


def test_registrar_cambio_estado_actualiza_el_estado():
    seguimiento = FabricaSeguimientos().crear_objeto({
        'trabajo_id': 't4', 'pais': 'CO', 'canal': 'app',
        'categoria': 'PLOMERIA', 'estado': 'CREADO', 'urgencia': 'NORMAL',
    })
    seguimiento.registrar_cambio_estado('ASIGNADO')
    assert seguimiento.estado_trabajo == 'ASIGNADO'
