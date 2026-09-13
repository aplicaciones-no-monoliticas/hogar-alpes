"""Agregación Emparejamiento — raíz con id = `trabajo_id` (§4.3 de la
especificación). Es CRUD, no Event Sourcing: se persiste el resultado final del
emparejamiento, no la secuencia de eventos que lo produjo.

La regla *«solo proveedores con acreditación ACREDITADA y vigente»* la aplica
la CONSULTA a la proyección (`infraestructura/repositorios.py`), no esta
agregación: los candidatos que `emparejar()` recibe ya vienen filtrados. Es la
misma separación de responsabilidades que el resto del servicio: el dominio
decide qué HACER con los candidatos (identificarlos o declarar que no hay),
no CUÁLES son candidatos.
"""
import uuid
from dataclasses import dataclass, field

from emparejamiento.seedwork.dominio.entidades import AgregacionRaiz
from emparejamiento.seedwork.dominio.mixins import ValidarReglasMixin

from .eventos import CandidatosIdentificados, SinCandidatos
from .objetos_valor import Candidato, CriterioBusqueda
from .reglas import CriterioBusquedaCompleto


@dataclass
class Emparejamiento(AgregacionRaiz, ValidarReglasMixin):
    trabajo_id: uuid.UUID = None
    region: str = ''
    criterio: CriterioBusqueda = field(default_factory=CriterioBusqueda)
    candidatos: list[Candidato] = field(default_factory=list)

    def emparejar(self, criterio: CriterioBusqueda, candidatos: list[Candidato]):
        self.validar_regla(CriterioBusquedaCompleto(criterio))
        self.criterio = criterio
        self.candidatos = list(candidatos)

        if candidatos:
            self.agregar_evento(
                CandidatosIdentificados(
                    trabajo_id=self.trabajo_id,
                    region=self.region,
                    categoria=criterio.categoria,
                    pais=criterio.pais,
                    ciudad=criterio.ciudad,
                    proveedores_id=[c.proveedor_id for c in candidatos],
                )
            )
        else:
            self.agregar_evento(
                SinCandidatos(
                    trabajo_id=self.trabajo_id,
                    region=self.region,
                    categoria=criterio.categoria,
                    pais=criterio.pais,
                    ciudad=criterio.ciudad,
                )
            )
