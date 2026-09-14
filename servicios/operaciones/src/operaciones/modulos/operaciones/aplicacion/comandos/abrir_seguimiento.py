"""Comando AbrirSeguimiento — interno, traducido por la capa anticorrupción
(OPS-2) desde `TrabajoCreado` en `evt-trabajo-.*`. Nunca llega por HTTP.

Idempotente por dos caminos, porque la entrega es al-menos-una-vez (RNF-4):
por `evento_id` (la reentrega exacta del mismo mensaje) y por `trabajo_id`
(si, por lo que fuera, el mismo trabajo generara dos `TrabajoCreado`). En
ambos casos el resultado es DUPLICADO y no se abre un segundo seguimiento.
"""
from dataclasses import dataclass

from operaciones.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from operaciones.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.fabricas import FabricaSeguimientos
from ...dominio.repositorios import RepositorioEventosProcesados, RepositorioSeguimientos
from .base import OperacionesBaseHandler

TIPO = 'TrabajoCreado'


@dataclass
class AbrirSeguimiento(Comando):
    evento_id: str = ''
    trabajo_id: str = ''
    pais: str = ''
    canal: str = ''
    categoria: str = ''
    estado: str = ''
    urgencia: str = ''


class AbrirSeguimientoHandler(OperacionesBaseHandler):
    def handle(self, comando: AbrirSeguimiento) -> str:
        repo_eventos = self.fabrica_repositorio.crear_objeto(RepositorioEventosProcesados)
        if repo_eventos.ya_procesado(comando.evento_id):
            return 'DUPLICADO'

        repo_seguimientos = self.fabrica_repositorio.crear_objeto(RepositorioSeguimientos)
        if repo_seguimientos.obtener_por_trabajo(comando.trabajo_id):
            UnidadTrabajoPuerto.registrar_batch(
                repo_eventos.registrar, comando.evento_id, TIPO, 'DUPLICADO'
            )
            UnidadTrabajoPuerto.commit()
            return 'DUPLICADO'

        seguimiento = FabricaSeguimientos().crear_objeto({
            'trabajo_id': comando.trabajo_id,
            'pais': comando.pais,
            'canal': comando.canal,
            'categoria': comando.categoria,
            'estado': comando.estado,
            'urgencia': comando.urgencia,
        })
        UnidadTrabajoPuerto.registrar_batch(repo_seguimientos.agregar, seguimiento)
        UnidadTrabajoPuerto.registrar_batch(
            repo_eventos.registrar, comando.evento_id, TIPO, 'APLICADO'
        )
        UnidadTrabajoPuerto.commit()
        return 'APLICADO'


@ejecutar_comando.register(AbrirSeguimiento)
def ejecutar_comando_abrir_seguimiento(comando: AbrirSeguimiento):
    return AbrirSeguimientoHandler().handle(comando)
