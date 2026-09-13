"""Reglas de negocio de la agregación Acreditacion."""
from acreditacion.seedwork.dominio.reglas import ReglaNegocio

from .objetos_valor import EstadoAcreditacion, Estado


class TransicionDeEstadoAcreditacionValida(ReglaNegocio):
    def __init__(self, actual: EstadoAcreditacion, destino: Estado, mensaje=None):
        super().__init__(
            mensaje or f'No se puede pasar de {actual.valor.value} a {destino.value}'
        )
        self.actual = actual
        self.destino = destino

    def es_valido(self) -> bool:
        return self.actual.puede_transicionar_a(self.destino)


class HomologacionesNoVacias(ReglaNegocio):
    def __init__(self, categorias: list[str], mensaje='La solicitud debe incluir al menos una categoría'):
        super().__init__(mensaje)
        self.categorias = categorias

    def es_valido(self) -> bool:
        return bool(self.categorias)
