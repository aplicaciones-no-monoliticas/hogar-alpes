"""Lado de ESCRITURA del patrón CQS.

Un comando expresa una intención y no devuelve datos. El despacho se resuelve
por tipo con `singledispatch`, de modo que el llamador no conoce al handler.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import singledispatch


@dataclass
class Comando(ABC):
    ...


class ComandoHandler(ABC):
    @abstractmethod
    def handle(self, comando: Comando):
        ...


@singledispatch
def ejecutar_comando(comando):
    raise NotImplementedError(
        f'No existe implementación para el comando de tipo {type(comando).__name__}'
    )
