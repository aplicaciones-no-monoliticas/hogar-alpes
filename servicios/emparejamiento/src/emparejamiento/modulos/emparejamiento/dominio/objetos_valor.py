"""Objetos valor del contexto Emparejamiento y Publicación."""
from dataclasses import dataclass

from emparejamiento.seedwork.dominio.objetos_valor import ObjetoValor


@dataclass(frozen=True)
class CriterioBusqueda(ObjetoValor):
    categoria: str = ''
    pais: str = ''
    ciudad: str = ''


@dataclass(frozen=True)
class Candidato(ObjetoValor):
    """Un proveedor que la proyección de Acreditación entregó como
    `ACREDITADA` y vigente para este criterio. `nivel` viaja como texto,
    igual que en el resto de los contratos (RS-5)."""
    proveedor_id: str = ''
    nivel: str = ''
