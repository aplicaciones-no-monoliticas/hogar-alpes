"""Fábrica del agregado Acreditacion.

Garantiza que una Acreditacion nunca exista en un estado inválido: si la regla
de negocio falla, la agregación no llega a construirse (mismo patrón que
`FabricaTrabajos` en Gestión de Trabajos)."""
from dataclasses import dataclass

from acreditacion.seedwork.dominio.fabricas import Fabrica

from .entidades import Acreditacion
from .excepciones import AcreditacionNoExisteExcepcion


@dataclass
class FabricaAcreditaciones(Fabrica):
    def crear_objeto(self, obj, mapeador=None) -> Acreditacion:
        if not isinstance(obj, dict):
            raise AcreditacionNoExisteExcepcion(
                'La fábrica de Acreditacion espera los datos de la solicitud'
            )
        return Acreditacion.solicitar(
            proveedor_id=obj.get('proveedor_id', ''),
            pais=obj.get('pais', ''),
            ciudad=obj.get('ciudad', ''),
            categorias=obj.get('categorias', []),
            nivel=obj.get('nivel', ''),
            vigencia_meses=obj.get('vigencia_meses', 0),
            motivo=obj.get('motivo', ''),
        )
