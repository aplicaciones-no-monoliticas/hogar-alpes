"""Objetos valor: sin identidad, inmutables, comparados por valor."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ObjetoValor:
    ...
