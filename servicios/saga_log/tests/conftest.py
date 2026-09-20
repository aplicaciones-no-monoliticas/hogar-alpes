"""`saga_log` nunca publica nada (CA-1.16): no hay `Despachador` que mockear
aquí, a diferencia de los otros cuatro servicios."""
import pytest

from saga_log import crear_app


@pytest.fixture
def app():
    app = crear_app({'TESTING': True})
    with app.app_context():
        yield app
