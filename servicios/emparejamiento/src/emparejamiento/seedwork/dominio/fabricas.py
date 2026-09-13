from abc import ABC, abstractmethod


class Fabrica(ABC):
    """Encapsula el ensamblaje de agregaciones complejas y garantiza que nazcan
    en un estado válido."""

    @abstractmethod
    def crear_objeto(self, obj, mapeador=None):
        ...
