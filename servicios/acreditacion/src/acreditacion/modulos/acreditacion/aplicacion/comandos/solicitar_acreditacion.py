"""Comando SolicitarAcreditacion — el lado de escritura del CQS.

`acreditacion_id` es opcional y lo genera el productor (comando por tópico o
por HTTP), igual que `trabajo_id` en Gestión de Trabajos: da la clave de
partición desde el primer mensaje y hace la creación idempotente ante
reintentos del productor.
"""
import uuid
from dataclasses import dataclass, field

from acreditacion.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from acreditacion.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.entidades import Acreditacion
from ...dominio.repositorios import RepositorioAcreditaciones
from .base import AcreditacionBaseHandler


@dataclass
class SolicitarAcreditacion(Comando):
    proveedor_id: str = ''
    pais: str = ''
    ciudad: str = ''
    categorias: list[str] = field(default_factory=list)
    nivel: str = ''
    vigencia_meses: int = 0
    motivo: str = ''
    acreditacion_id: str = ''


class SolicitarAcreditacionHandler(AcreditacionBaseHandler):
    def handle(self, comando: SolicitarAcreditacion) -> str:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioAcreditaciones)

        if comando.acreditacion_id:
            existente = repositorio.obtener_por_id(comando.acreditacion_id)
            if existente:
                # Idempotente: el mismo comando reentregado no crea una
                # segunda acreditación.
                return str(existente.id)

        acreditacion = Acreditacion.solicitar(
            proveedor_id=comando.proveedor_id,
            pais=comando.pais,
            ciudad=comando.ciudad,
            categorias=comando.categorias,
            nivel=comando.nivel,
            vigencia_meses=comando.vigencia_meses,
            motivo=comando.motivo,
            id=uuid.UUID(comando.acreditacion_id) if comando.acreditacion_id else None,
        )

        UnidadTrabajoPuerto.registrar_batch(repositorio.agregar, acreditacion)
        UnidadTrabajoPuerto.commit()
        return str(acreditacion.id)


@ejecutar_comando.register(SolicitarAcreditacion)
def ejecutar_comando_solicitar_acreditacion(comando: SolicitarAcreditacion):
    return SolicitarAcreditacionHandler().handle(comando)
