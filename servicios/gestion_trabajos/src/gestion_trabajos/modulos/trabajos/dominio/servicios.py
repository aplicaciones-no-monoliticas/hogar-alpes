"""Puerto hacia el sidecar de reglas regionales.

Sustenta el escenario 2: incorporar un país nuevo se resuelve configurando el
sidecar, sin tocar ni redesplegar este servicio. El dominio declara qué necesita
saber; la infraestructura resuelve de dónde sale.
"""
from abc import ABC, abstractmethod

from gestion_trabajos.seedwork.dominio.servicios import ServicioDominio


class ServicioReglasRegionales(ServicioDominio, ABC):
    @abstractmethod
    def categorias_permitidas(self, pais: str) -> list[str]:
        ...

    @abstractmethod
    def urgencias_permitidas(self, pais: str) -> list[str]:
        ...
