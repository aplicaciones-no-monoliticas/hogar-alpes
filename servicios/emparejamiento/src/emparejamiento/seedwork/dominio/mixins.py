from .excepciones import ReglaNegocioExcepcion
from .reglas import ReglaNegocio


class ValidarReglasMixin:
    """Permite que una agregación se valide a sí misma antes de mutar su estado."""

    def validar_regla(self, regla: ReglaNegocio):
        if not regla.es_valido():
            raise ReglaNegocioExcepcion(regla, regla.mensaje())
