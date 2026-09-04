"""El adaptador del sidecar regional (escenario 2)."""
from gestion_trabajos.modulos.trabajos.infraestructura.reglas_regionales import (
    SidecarReglasRegionales,
)


def test_cada_pais_trae_sus_propias_categorias():
    sidecar = SidecarReglasRegionales()
    assert 'SINIESTRO_GRANIZO' in sidecar.categorias_permitidas('CO')
    assert 'SINIESTRO_GRANIZO' not in sidecar.categorias_permitidas('MX')
    assert 'SISMO' in sidecar.categorias_permitidas('MX')


def test_pais_desconocido_cae_al_contrato_por_defecto():
    sidecar = SidecarReglasRegionales()
    assert sidecar.categorias_permitidas('PE') == sidecar.categorias_permitidas('_default')
    assert sidecar.urgencias_permitidas('PE')
