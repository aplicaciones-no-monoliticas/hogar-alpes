"""Agregación Acreditacion — Event Sourcing (D-5 de la especificación).

No hay un solo `estado` mutado en el sitio: cada transición se expresa como un
evento (`_registrar_evento`), que a la vez **muta el estado en memoria**
(`aplicar_evento`) y queda pendiente de persistirse como una fila nueva del
event store. Reconstruir la agregación —`obtener_por_id` en el repositorio de
infraestructura— es reproducir esos mismos eventos en orden desde la versión 0.

Por eso `aplicar_evento` está separado de los métodos de comando
(`solicitar`/`aprobar`/`revocar`): el primero es la única lógica de mutación de
estado y se ejecuta tanto al reproducir el historial como al registrar un
evento nuevo. Los métodos de comando son los que además **validan** la regla de
negocio antes de emitir.
"""
from dataclasses import dataclass, field

from acreditacion.seedwork.dominio.entidades import AgregacionRaiz
from acreditacion.seedwork.dominio.mixins import ValidarReglasMixin

from .eventos import AcreditacionAprobada, AcreditacionRevocada, AcreditacionSolicitada
from .objetos_valor import Estado, EstadoAcreditacion
from .reglas import HomologacionesNoVacias, TransicionDeEstadoAcreditacionValida


def _sumar_meses(meses: int) -> str:
    """Vigencia aproximada: 30 días por mes. Suficiente para la POC — no hay
    dependencia nueva que agregar por un cálculo de calendario exacto."""
    from datetime import date, timedelta

    return (date.today() + timedelta(days=30 * max(meses, 0))).isoformat()


@dataclass
class Acreditacion(AgregacionRaiz, ValidarReglasMixin):
    proveedor_id: str = ''
    pais: str = ''
    ciudad: str = ''
    categorias: list[str] = field(default_factory=list)
    nivel: str = ''
    vigencia_meses: int = 0
    vigente_hasta: str = ''
    motivo: str = ''
    estado: EstadoAcreditacion = field(default_factory=EstadoAcreditacion)
    # Última versión PERSISTIDA de este agregado. 0 para uno nuevo, todavía sin
    # eventos escritos. La usa el repositorio para el control de concurrencia
    # optimista (`UNIQUE(agregado_id, version)`).
    version: int = 0

    @classmethod
    def solicitar(
        cls, proveedor_id: str, pais: str, ciudad: str, categorias: list[str],
        nivel: str, vigencia_meses: int, motivo: str = '', id=None,
    ) -> 'Acreditacion':
        """`id` es opcional: si el productor del comando ya trae un
        `acreditacion_id` (igual que `trabajo_id` en Gestión de Trabajos), la
        creación es idempotente ante reintentos — lo valida el handler de
        aplicación consultando el repositorio antes de llamar aquí."""
        kwargs = dict(
            proveedor_id=proveedor_id, pais=pais, ciudad=ciudad,
            categorias=list(categorias), nivel=nivel, vigencia_meses=vigencia_meses,
        )
        if id is not None:
            kwargs['id'] = id
        acreditacion = cls(**kwargs)
        acreditacion.validar_regla(HomologacionesNoVacias(acreditacion.categorias))
        acreditacion._registrar_evento(AcreditacionSolicitada, motivo=motivo)
        return acreditacion

    def aprobar(self, motivo: str = ''):
        self.validar_regla(
            TransicionDeEstadoAcreditacionValida(self.estado, Estado.ACREDITADA)
        )
        self.vigente_hasta = _sumar_meses(self.vigencia_meses)
        self._registrar_evento(AcreditacionAprobada, motivo=motivo)

    def revocar(self, motivo: str = ''):
        self.validar_regla(
            TransicionDeEstadoAcreditacionValida(self.estado, Estado.REVOCADA)
        )
        self._registrar_evento(AcreditacionRevocada, motivo=motivo)

    def _registrar_evento(self, tipo, motivo: str = ''):
        destino = {
            AcreditacionSolicitada: Estado.SOLICITADA,
            AcreditacionAprobada: Estado.ACREDITADA,
            AcreditacionRevocada: Estado.REVOCADA,
        }[tipo]
        evento = tipo(
            agregado_id=self.id,
            version=self.version + 1,
            proveedor_id=self.proveedor_id,
            pais=self.pais,
            ciudad=self.ciudad,
            categorias=list(self.categorias),
            nivel=self.nivel,
            vigencia_meses=self.vigencia_meses,
            estado=destino.value,
            vigente_hasta=self.vigente_hasta,
            motivo=motivo,
        )
        self.aplicar_evento(evento)
        self.agregar_evento(evento)

    def aplicar_evento(self, evento):
        """Muta el estado en memoria. Se usa tanto al reproducir el historial
        (repositorio) como al registrar un evento nuevo (arriba): la mutación es
        idéntica en los dos casos, que es justo lo que garantiza que reproducir
        el log reconstruya el mismo estado."""
        self.proveedor_id = evento.proveedor_id
        self.pais = evento.pais
        self.ciudad = evento.ciudad
        self.categorias = list(evento.categorias)
        self.nivel = evento.nivel
        self.vigencia_meses = evento.vigencia_meses
        self.vigente_hasta = evento.vigente_hasta
        self.motivo = evento.motivo
        self.estado = EstadoAcreditacion(Estado(evento.estado))
        self.version = evento.version
