"""Excepciones base del dominio. Ninguna conoce infraestructura."""


class ExcepcionDominio(Exception):
    ...


class ReglaNegocioExcepcion(ExcepcionDominio):
    def __init__(self, regla, mensaje: str = 'Se ha roto una regla de negocio'):
        self.regla = regla
        super().__init__(mensaje)


class ExcepcionFabrica(ExcepcionDominio):
    ...


class TipoObjetoNoExisteEnDominioTrabajosExcepcion(ExcepcionFabrica):
    def __init__(self, mensaje='No existe una fábrica para el tipo de objeto solicitado'):
        super().__init__(mensaje)
