from abc import ABC
from dataclasses import dataclass


@dataclass(frozen=True)
class DTO(ABC):
    """Estructura de transporte entre capas. No tiene comportamiento de dominio."""
    ...
