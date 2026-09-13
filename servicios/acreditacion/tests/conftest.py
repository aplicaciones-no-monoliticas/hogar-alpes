"""Las pruebas de este servicio no dependen de un clúster de Pulsar real —esa
integración se verifica aparte, contra un broker vivo, con
`herramientas/verificar_contratos.py` y `escenarios/esquemas.py`—. Aquí se
reemplaza la publicación por un no-op para que la suite sea rápida y
determinista incluso sin `docker compose up` corriendo.
"""
import pytest


@pytest.fixture(autouse=True)
def _sin_broker(monkeypatch):
    from acreditacion.seedwork.infraestructura import despachadores

    monkeypatch.setattr(despachadores.Despachador, 'publicar_evento', lambda self, *a, **k: None)
