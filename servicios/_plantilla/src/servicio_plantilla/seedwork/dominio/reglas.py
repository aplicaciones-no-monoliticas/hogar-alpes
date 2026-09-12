"""Patrón de especificación aplicado a reglas de negocio (Evans, cap. 9)."""
from abc import ABC, abstractmethod


class ReglaNegocio(ABC):
    __mensaje: str = 'La regla de negocio no se cumple'

    def __init__(self, mensaje: str | None = None):
        if mensaje:
            self.__mensaje = mensaje

    def mensaje(self) -> str:
        return self.__mensaje

    @abstractmethod
    def es_valido(self) -> bool:
        ...

    def __str__(self) -> str:
        return f'{type(self).__name__} - {self.__mensaje}'
