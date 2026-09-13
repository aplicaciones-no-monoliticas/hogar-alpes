"""Comando AprobarAcreditacion.

Idempotente a propósito: si el comando se reentrega (`cmd-acreditacion` es
Failover, pero un `negative_acknowledge` tras un fallo transitorio lo reintenta
igual), aprobar una acreditación que YA está `ACREDITADA` no es un error de
transición — es la misma orden llegando dos veces. Solo se rechaza la
transición que de verdad es inválida (por ejemplo, aprobar una `REVOCADA`).
"""
from dataclasses import dataclass

from acreditacion.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from acreditacion.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.excepciones import AcreditacionNoExisteExcepcion
from ...dominio.objetos_valor import Estado
from ...dominio.repositorios import RepositorioAcreditaciones
from .base import AcreditacionBaseHandler


@dataclass
class AprobarAcreditacion(Comando):
    acreditacion_id: str = ''
    motivo: str = ''


class AprobarAcreditacionHandler(AcreditacionBaseHandler):
    def handle(self, comando: AprobarAcreditacion) -> str:
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioAcreditaciones)
        acreditacion = repositorio.obtener_por_id(comando.acreditacion_id)
        if not acreditacion:
            raise AcreditacionNoExisteExcepcion()

        if acreditacion.estado.valor == Estado.ACREDITADA:
            return str(acreditacion.id)

        acreditacion.aprobar(motivo=comando.motivo)
        UnidadTrabajoPuerto.registrar_batch(repositorio.agregar, acreditacion)
        UnidadTrabajoPuerto.commit()
        return str(acreditacion.id)


@ejecutar_comando.register(AprobarAcreditacion)
def ejecutar_comando_aprobar_acreditacion(comando: AprobarAcreditacion):
    return AprobarAcreditacionHandler().handle(comando)
