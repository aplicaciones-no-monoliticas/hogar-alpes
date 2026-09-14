"""GT-7 — las pruebas de este servicio no dependen de un clúster de Pulsar
real —esa integración se verifica aparte, con `herramientas/verificar_contratos.py`
y los escenarios—. Aquí se reemplaza la publicación por un no-op, igual que en
`operaciones`, `emparejamiento` y `acreditacion` (`tests/conftest.py` de cada
uno). Faltaba en Gestión de Trabajos: sin este mock, cada prueba que crea un
trabajo intenta conectarse a un broker inexistente y la suite tarda minutos en
vez de segundos esperando el `operation_timeout_seconds` de cada intento.
"""
import pytest


@pytest.fixture(autouse=True)
def _sin_broker(monkeypatch):
    from gestion_trabajos.seedwork.infraestructura import despachadores

    monkeypatch.setattr(despachadores.Despachador, 'publicar_evento', lambda self, *a, **k: None)
