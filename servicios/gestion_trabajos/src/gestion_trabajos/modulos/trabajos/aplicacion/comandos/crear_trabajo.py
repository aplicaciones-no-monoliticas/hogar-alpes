"""Comando CrearTrabajo — el lado de escritura del CQS.

El handler no persiste: registra la operación en la Unidad de Trabajo y hace
commit. La UoW publica los eventos de dominio antes del commit (para el módulo
`operaciones`) y los de integración después (para el broker).
"""
from dataclasses import dataclass, field

from gestion_trabajos.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from gestion_trabajos.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.entidades import Trabajo
from ...dominio.repositorios import RepositorioTrabajos
from ...infraestructura.reglas_regionales import SidecarReglasRegionales
from ..dto import TrabajoDTO
from ..mapeadores import MapeadorTrabajoDTOJson
from .base import TrabajoBaseHandler


@dataclass
class CrearTrabajo(Comando):
    canal: str = ''
    partner_id: str = ''
    referencia_externa: str = ''
    categoria: str = ''
    urgencia: str = 'NORMAL'
    pais: str = ''
    ciudad: str = ''
    direccion: str = ''
    descripcion: str = ''


class CrearTrabajoHandler(TrabajoBaseHandler):
    def handle(self, comando: CrearTrabajo) -> str:
        trabajo_dto = TrabajoDTO(
            canal=comando.canal,
            partner_id=comando.partner_id,
            referencia_externa=comando.referencia_externa,
            categoria=comando.categoria,
            urgencia=comando.urgencia,
            pais=comando.pais,
            ciudad=comando.ciudad,
            direccion=comando.direccion,
            descripcion=comando.descripcion,
        )

        trabajo: Trabajo = self.fabrica_trabajos.crear_objeto(
            trabajo_dto, MapeadorTrabajoDTOJson()
        )

        # Las reglas del país entran por el puerto del sidecar. Si mañana entra
        # Perú, se configura el sidecar y este archivo no cambia.
        sidecar = SidecarReglasRegionales()
        trabajo.crear(
            categorias_permitidas=sidecar.categorias_permitidas(comando.pais),
            urgencias_permitidas=sidecar.urgencias_permitidas(comando.pais),
        )

        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)

        UnidadTrabajoPuerto.registrar_batch(repositorio.agregar, trabajo)
        UnidadTrabajoPuerto.commit()

        return str(trabajo.id)


@ejecutar_comando.register(CrearTrabajo)
def ejecutar_comando_crear_trabajo(comando: CrearTrabajo):
    return CrearTrabajoHandler().handle(comando)
