"""Reglas de negocio de la agregación Trabajo."""
from gestion_trabajos.seedwork.dominio.reglas import ReglaNegocio

from .objetos_valor import Categoria, Estado, EstadoTrabajo, Ubicacion, Urgencia


class TransicionDeEstadoValida(ReglaNegocio):
    def __init__(self, actual: EstadoTrabajo, destino: Estado, mensaje=None):
        super().__init__(
            mensaje or f'No se puede pasar de {actual.valor.value} a {destino.value}'
        )
        self.actual = actual
        self.destino = destino

    def es_valido(self) -> bool:
        return self.actual.puede_transicionar_a(self.destino)


class CategoriaPermitidaEnRegion(ReglaNegocio):
    """La lista de categorías la aporta el sidecar regional. El dominio solo
    exige que la categoría esté en la lista que le entregaron."""

    def __init__(self, categoria: Categoria, permitidas: list[str], mensaje=None):
        super().__init__(
            mensaje or f'La categoría {categoria.codigo} no aplica en esta región'
        )
        self.categoria = categoria
        self.permitidas = permitidas

    def es_valido(self) -> bool:
        return self.categoria.codigo in self.permitidas


class UrgenciaPermitidaEnRegion(ReglaNegocio):
    def __init__(self, urgencia: Urgencia, permitidas: list[str], mensaje=None):
        super().__init__(
            mensaje or f'El nivel de urgencia {urgencia.nivel} no aplica en esta región'
        )
        self.urgencia = urgencia
        self.permitidas = permitidas

    def es_valido(self) -> bool:
        return self.urgencia.nivel in self.permitidas


class UbicacionCompleta(ReglaNegocio):
    def __init__(self, ubicacion: Ubicacion, mensaje='La ubicación del trabajo está incompleta'):
        super().__init__(mensaje)
        self.ubicacion = ubicacion

    def es_valido(self) -> bool:
        return bool(self.ubicacion.pais and self.ubicacion.ciudad and self.ubicacion.direccion)
