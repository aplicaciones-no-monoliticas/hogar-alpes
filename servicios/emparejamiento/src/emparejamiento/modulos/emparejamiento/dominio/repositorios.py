"""Puertos de salida del dominio.

Dos repositorios porque son dos modelos distintos, aunque compartan base de
datos (§7 de la especificación): `RepositorioEmparejamientos` es el lado de
escritura de la agregación; `RepositorioProveedoresCandidatos` es la
PROYECCIÓN de lectura que alimenta `evt-acreditacion` — no es una copia del
modelo de Acreditación, es la forma que este servicio necesita para buscar
(capa anticorrupción, §4.3).
"""
from abc import ABC, abstractmethod
from uuid import UUID

from .entidades import Emparejamiento


class RepositorioEmparejamientos(ABC):
    @abstractmethod
    def obtener_por_trabajo(self, trabajo_id: UUID | str) -> Emparejamiento | None:
        ...

    @abstractmethod
    def agregar(self, emparejamiento: Emparejamiento):
        ...


class RepositorioProveedoresCandidatos(ABC):
    @abstractmethod
    def buscar(self, categoria: str, pais: str, ciudad: str) -> list[dict]:
        """Solo proveedores `ACREDITADA` y vigentes — la regla de negocio del
        emparejamiento, aplicada aquí porque es sobre la PROYECCIÓN, no sobre
        la agregación de escritura."""
        ...

    @abstractmethod
    def upsert(self, proveedor_id: str, categoria: str, pais: str, ciudad: str,
               nivel: str, estado: str, vigente_hasta: str, version: int):
        """Idempotente y tolerante al desorden: se aplica solo si `version` es
        mayor que la almacenada (§5.3 de la especificación)."""
        ...
