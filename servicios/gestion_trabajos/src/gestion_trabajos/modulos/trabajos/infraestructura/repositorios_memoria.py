"""Segundo adaptador de `RepositorioTrabajos` — MOD-1 (CA-M1, G-5).

Guarda las agregaciones **en memoria del proceso**, sin SQLAlchemy ni
PostgreSQL. Existe para demostrar el escenario, no como optimización: prueba
que reemplazar el adaptador de persistencia es un archivo nuevo aquí y una
línea en `fabricas.py`, sin tocar `dominio/` ni `aplicacion/`.

Es el mismo adaptador que usan las pruebas de la capa de aplicación
(`tests/test_aplicacion_trabajos.py`): no es un adaptador de juguete que solo
sirve para la demo del escenario 1, es el que sostiene la suite.
"""
import copy
from uuid import UUID

from ..dominio.entidades import Trabajo
from ..dominio.repositorios import RepositorioTrabajos


class RepositorioTrabajosMemoria(RepositorioTrabajos):
    """Un diccionario por INSTANCIA, no de clase: cada `crear_objeto()` de la
    fábrica parte de un repositorio vacío salvo que alguien lo comparta a
    propósito (ver `_ALMACEN` más abajo, para las pruebas)."""

    # Compartido entre instancias dentro del MISMO proceso, para que un
    # comando y una consulta —cada uno crea su propio repositorio— vean el
    # mismo estado. Es la simplificación que acepta un adaptador en memoria:
    # no hay otro proceso con el que sincronizar.
    _ALMACEN: dict[str, Trabajo] = {}

    def obtener_por_id(self, id) -> Trabajo:
        return self._ALMACEN.get(str(id))

    def obtener_todos(self) -> list[Trabajo]:
        return list(self._ALMACEN.values())

    def obtener_por_estado(self, estado: str) -> list[Trabajo]:
        return [t for t in self._ALMACEN.values() if t.estado.valor.value == estado]

    def agregar(self, trabajo: Trabajo):
        self._ALMACEN[str(trabajo.id)] = copy.deepcopy(trabajo)

    def actualizar(self, trabajo: Trabajo):
        self._ALMACEN[str(trabajo.id)] = copy.deepcopy(trabajo)

    def eliminar(self, id: UUID):
        self._ALMACEN.pop(str(id), None)

    @classmethod
    def limpiar(cls):
        """Para pruebas: cada caso arranca de un almacén vacío."""
        cls._ALMACEN = {}
