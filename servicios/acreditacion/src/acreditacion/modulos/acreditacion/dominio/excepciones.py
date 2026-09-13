from acreditacion.seedwork.dominio.excepciones import ExcepcionDominio


class AcreditacionNoExisteExcepcion(ExcepcionDominio):
    def __init__(self, mensaje='No existe una acreditación con ese identificador'):
        super().__init__(mensaje)


class ConflictoDeConcurrenciaExcepcion(ExcepcionDominio):
    """El event store rechazó la escritura: alguien más ya escribió esa versión
    del agregado (`UNIQUE(agregado_id, version)`, ACR-2)."""

    def __init__(self, mensaje='Conflicto de concurrencia: la versión ya fue escrita'):
        super().__init__(mensaje)
