from abc import ABC, abstractmethod

from .dto import DTO


class Mapeador(ABC):
    @abstractmethod
    def obtener_tipo(self) -> type:
        ...

    @abstractmethod
    def entidad_a_dto(self, entidad) -> DTO:
        ...

    @abstractmethod
    def dto_a_entidad(self, dto: DTO):
        ...
