"""Comando ConfirmarVigencia — paso 3 de ida de la saga (D2/D4 de research.md).

No muta el agregado `Acreditacion`: solo consulta la proyección de lectura
`vigencia_por_proveedor` y publica el resultado. Por eso no pasa por la Unidad
de Trabajo ni por el mecanismo de eventos de dominio — no hay nada que
comprometer en una transacción de negocio, es una traducción de una consulta a
un mensaje saliente (igual de idempotente en ambos sentidos: consultar y
publicar de nuevo ante una reentrega no cambia nada persistido).
"""
from dataclasses import dataclass

from acreditacion.config.topicos import topico_evt_acreditacion
from acreditacion.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from acreditacion.seedwork.infraestructura.despachadores import Despachador

from ...dominio.repositorios import RepositorioVigenciaPorProveedor
from ...infraestructura.mapeadores import MapeadorVigenciaIntegracion
from .base import AcreditacionBaseHandler


@dataclass
class ConfirmarVigencia(Comando):
    trabajo_id: str = ''
    proveedor_id: str = ''
    categoria: str = ''
    # Marca de demostración de la saga (D3 de research.md): nunca forma parte
    # de ningún contrato, solo viaja como propiedad del mensaje.
    simular_fallo: str = ''


@dataclass
class DecisionVigencia:
    """No es un evento de dominio (no hay agregado que lo emita): es el
    resultado de la consulta que `MapeadorVigenciaIntegracion` traduce al
    esquema Avro de `evt-acreditacion`."""
    trabajo_id: str = ''
    proveedor_id: str = ''
    categoria: str = ''
    confirmada: bool = False


class ConfirmarVigenciaHandler(AcreditacionBaseHandler):
    def handle(self, comando: ConfirmarVigencia):
        repo = self.fabrica_repositorio.crear_objeto(RepositorioVigenciaPorProveedor)
        vigencia = repo.consultar(comando.proveedor_id, comando.categoria)

        # D3/T034 (US2): la marca VIGENCIA rechaza sin consultar el estado
        # real del proveedor.
        confirmada = (
            comando.simular_fallo != 'VIGENCIA'
            and vigencia is not None
            and vigencia['estado'] == 'ACREDITADA'
            and vigencia['vigente_hasta'] >= _hoy()
        )

        decision = DecisionVigencia(
            trabajo_id=comando.trabajo_id, proveedor_id=comando.proveedor_id,
            categoria=comando.categoria, confirmada=confirmada,
        )
        propiedades = {}
        if comando.simular_fallo:
            propiedades['simular_fallo'] = comando.simular_fallo

        Despachador().publicar_evento(
            decision, topico_evt_acreditacion(), MapeadorVigenciaIntegracion(),
            clave=comando.proveedor_id, propiedades=propiedades,
        )


def _hoy() -> str:
    from datetime import date
    return date.today().isoformat()


@ejecutar_comando.register(ConfirmarVigencia)
def ejecutar_comando_confirmar_vigencia(comando: ConfirmarVigencia):
    return ConfirmarVigenciaHandler().handle(comando)
