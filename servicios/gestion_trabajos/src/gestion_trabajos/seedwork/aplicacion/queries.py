"""Lado de LECTURA del patrón CQS.

Una consulta devuelve datos y no muta estado. Se mantiene síncrona a propósito:
el material del curso lo señala como el caso normal.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import singledispatch
from typing import Any


@dataclass
class Query(ABC):
    ...


@dataclass
class QueryResultado:
    resultado: Any = field(default=None)


class QueryHandler(ABC):
    @abstractmethod
    def handle(self, query: Query) -> QueryResultado:
        ...


@singledispatch
def ejecutar_query(query) -> QueryResultado:
    raise NotImplementedError(
        f'No existe implementación para la consulta de tipo {type(query).__name__}'
    )
