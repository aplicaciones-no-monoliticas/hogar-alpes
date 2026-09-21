"""Comando LiberarReserva — reversión del paso 2 de la saga (D1 de research.md).

Disparado por `vigencia-rechazada` (US2, T036) o por una cancelación de
asignación final (US2, T041). Idempotente ante reentrega: si el trabajo ya no
tiene una reserva activa (porque ya se liberó), es un no-op — ni borra nada
otra vez ni vuelve a publicar `candidatos-liberados`.
"""
from dataclasses import dataclass

from emparejamiento.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from emparejamiento.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.repositorios import RepositorioEmparejamientos, RepositorioReservasProveedor
from .base import EmparejamientoBaseHandler


@dataclass
class LiberarReserva(Comando):
    trabajo_id: str = ''
    motivo: str = ''


class LiberarReservaHandler(EmparejamientoBaseHandler):
    def handle(self, comando: LiberarReserva):
        repo_emparejamientos = self.fabrica_repositorio.crear_objeto(RepositorioEmparejamientos)
        emparejamiento = repo_emparejamientos.obtener_por_trabajo(comando.trabajo_id)

        if not emparejamiento or not emparejamiento.proveedor_reservado:
            # No hay nada que liberar: o nunca hubo reserva (SIN_CANDIDATOS),
            # o una reentrega llega después de que ya se liberó.
            return

        repo_reservas = self.fabrica_repositorio.crear_objeto(RepositorioReservasProveedor)
        repo_reservas.liberar_por_trabajo(comando.trabajo_id)
        emparejamiento.liberar_reserva(comando.motivo)

        UnidadTrabajoPuerto.registrar_batch(repo_emparejamientos.actualizar, emparejamiento)
        UnidadTrabajoPuerto.commit()


@ejecutar_comando.register(LiberarReserva)
def ejecutar_comando_liberar_reserva(comando: LiberarReserva):
    return LiberarReservaHandler().handle(comando)
