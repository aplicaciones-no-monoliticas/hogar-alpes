"""Comando EmparejarTrabajo — interno, disparado por `TrabajoCreado`
(coreografía, el valor por defecto de `PS-5`). Lo ejecuta el consumidor
regional de `evt-trabajo-{región}` (EMP-3), nunca llega por HTTP.

Idempotente ante reentrega: si ya existe un emparejamiento para este
`trabajo_id`, el comando es un no-op — no se vuelve a consultar la proyección
ni se publica un segundo evento de integración.
"""
from dataclasses import dataclass

from emparejamiento.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from emparejamiento.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.fabricas import FabricaEmparejamientos
from ...dominio.objetos_valor import Candidato, CriterioBusqueda
from ...dominio.repositorios import RepositorioEmparejamientos, RepositorioProveedoresCandidatos
from .base import EmparejamientoBaseHandler


@dataclass
class EmparejarTrabajo(Comando):
    trabajo_id: str = ''
    region: str = ''
    categoria: str = ''
    pais: str = ''
    ciudad: str = ''


class EmparejarTrabajoHandler(EmparejamientoBaseHandler):
    def handle(self, comando: EmparejarTrabajo) -> str:
        repo_emparejamientos = self.fabrica_repositorio.crear_objeto(RepositorioEmparejamientos)

        existente = repo_emparejamientos.obtener_por_trabajo(comando.trabajo_id)
        if existente:
            return str(existente.trabajo_id)

        repo_candidatos = self.fabrica_repositorio.crear_objeto(RepositorioProveedoresCandidatos)
        encontrados = repo_candidatos.buscar(comando.categoria, comando.pais, comando.ciudad)
        candidatos = [Candidato(proveedor_id=c['proveedor_id'], nivel=c['nivel']) for c in encontrados]

        emparejamiento = FabricaEmparejamientos().crear_objeto({
            'trabajo_id': comando.trabajo_id, 'region': comando.region,
        })
        criterio = CriterioBusqueda(categoria=comando.categoria, pais=comando.pais, ciudad=comando.ciudad)
        emparejamiento.emparejar(criterio, candidatos)

        UnidadTrabajoPuerto.registrar_batch(repo_emparejamientos.agregar, emparejamiento)
        UnidadTrabajoPuerto.commit()
        return str(emparejamiento.trabajo_id)


@ejecutar_comando.register(EmparejarTrabajo)
def ejecutar_comando_emparejar_trabajo(comando: EmparejarTrabajo):
    return EmparejarTrabajoHandler().handle(comando)
