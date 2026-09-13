from emparejamiento.seedwork.dominio.excepciones import ExcepcionDominio


class EmparejamientoNoExisteExcepcion(ExcepcionDominio):
    def __init__(self, mensaje='No existe un emparejamiento para ese trabajo'):
        super().__init__(mensaje)
