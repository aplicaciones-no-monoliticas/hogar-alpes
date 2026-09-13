"""Comando ActualizarProveedorCandidato — la capa anticorrupción de la
proyección (EMP-2): traduce `AcreditacionActualizada` (evento externo, carga de
estado) a una actualización de `proveedores_candidatos`.

Una acreditación certifica varias categorías a la vez (`categorias[]` en el
contrato); la proyección tiene una fila por (proveedor, categoría), así que el
comando hace upsert de cada una por separado. `upsert` ya es tolerante al
desorden (ver `RepositorioProveedoresCandidatos`), así que este comando no
necesita saber si el evento llegó tarde.
"""
from dataclasses import dataclass, field

from emparejamiento.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from emparejamiento.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.repositorios import RepositorioProveedoresCandidatos
from .base import EmparejamientoBaseHandler


@dataclass
class ActualizarProveedorCandidato(Comando):
    proveedor_id: str = ''
    pais: str = ''
    ciudad: str = ''
    categorias: list[str] = field(default_factory=list)
    nivel: str = ''
    estado: str = ''
    vigente_hasta: str = ''
    version: int = 0


class ActualizarProveedorCandidatoHandler(EmparejamientoBaseHandler):
    def handle(self, comando: ActualizarProveedorCandidato):
        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioProveedoresCandidatos)

        for categoria in comando.categorias:
            UnidadTrabajoPuerto.registrar_batch(
                repositorio.upsert,
                proveedor_id=comando.proveedor_id, categoria=categoria,
                pais=comando.pais, ciudad=comando.ciudad, nivel=comando.nivel,
                estado=comando.estado, vigente_hasta=comando.vigente_hasta,
                version=comando.version,
            )
        UnidadTrabajoPuerto.commit()


@ejecutar_comando.register(ActualizarProveedorCandidato)
def ejecutar_comando_actualizar_proveedor_candidato(comando: ActualizarProveedorCandidato):
    return ActualizarProveedorCandidatoHandler().handle(comando)
