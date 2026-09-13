"""Comando RevocarAcreditacion. Idempotente igual que Aprobar (ver ese
módulo): revocar una ya `REVOCADA` no es un error de transición."""
from dataclasses import dataclass

from acreditacion.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from acreditacion.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.excepciones import AcreditacionNoExisteExcepcion
from ...dominio.objetos_valor import Estado
from ...dominio.repositorios import RepositorioAcreditaciones
from .base import AcreditacionBaseHandler


@dataclass
class RevocarAcreditacion(Comando):
    acreditacion_id: str = ''
    motivo: str = ''


class RevocarAcreditacionHandler(AcreditacionBaseHandler):
    def handle(self, comando: RevocarAcreditacion) -> str:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioAcreditaciones)
        acreditacion = repositorio.obtener_por_id(comando.acreditacion_id)
        if not acreditacion:
            raise AcreditacionNoExisteExcepcion()

        if acreditacion.estado.valor == Estado.REVOCADA:
            return str(acreditacion.id)

        acreditacion.revocar(motivo=comando.motivo)
        UnidadTrabajoPuerto.registrar_batch(repositorio.agregar, acreditacion)
        UnidadTrabajoPuerto.commit()
        return str(acreditacion.id)


@ejecutar_comando.register(RevocarAcreditacion)
def ejecutar_comando_revocar_acreditacion(comando: RevocarAcreditacion):
    return RevocarAcreditacionHandler().handle(comando)
