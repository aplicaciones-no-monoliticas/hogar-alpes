"""Comando CrearTrabajo — el lado de escritura del CQS.

El handler no persiste: registra la operación en la Unidad de Trabajo y hace
commit. La UoW publica los eventos de dominio antes del commit (para otros
módulos dentro de este mismo proceso, si los hay) y los de integración
después (para el broker — es como Operaciones se entera hoy, ya extraído a su
propio servicio desde GT-5).

**`trabajo_id` opcional (GT-4, CA-E1).** Lo genera el productor —el generador
de carga hoy, el Gateway de Partners en la Entrega 5—, no este servicio. Dos
consecuencias:

1. Da la clave de partición desde el primer mensaje del flujo (`cmd-trabajo-*`
   y `evt-trabajo-*` comparten `trabajo_id`).
2. La creación es **idempotente**: si el productor reintenta el mismo comando
   —por ejemplo, porque no vio la confirmación—, `CrearTrabajoHandler` lo
   reconoce y devuelve el trabajo que ya existe en vez de crear un segundo.
   Sin `trabajo_id` (los clientes HTTP que no lo mandan) no hay con qué
   deduplicar: cada `POST /trabajos` sin él crea un trabajo nuevo, como antes.
"""
from dataclasses import dataclass, field

from gestion_trabajos.seedwork.aplicacion.comandos import Comando, ejecutar_comando
from gestion_trabajos.seedwork.infraestructura.uow import UnidadTrabajoPuerto

from ...dominio.entidades import Trabajo
from ...dominio.objetos_valor import Estado
from ...dominio.repositorios import RepositorioTrabajos
from ...infraestructura.reglas_regionales import SidecarReglasRegionales
from ..dto import TrabajoDTO
from ..mapeadores import MapeadorTrabajoDTOJson
from .base import TrabajoBaseHandler


@dataclass
class CrearTrabajo(Comando):
    trabajo_id: str = ''
    canal: str = ''
    partner_id: str = ''
    referencia_externa: str = ''
    categoria: str = ''
    urgencia: str = 'NORMAL'
    pais: str = ''
    ciudad: str = ''
    direccion: str = ''
    descripcion: str = ''
    # Marca de demostración de la saga (Entrega 5, D3 de research.md): nunca
    # forma parte de ningún contrato, solo viaja como propiedad del mensaje.
    simular_fallo: str = ''


class CrearTrabajoHandler(TrabajoBaseHandler):
    def handle(self, comando: CrearTrabajo) -> str:
        if comando.trabajo_id:
            repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)
            existente = repositorio.obtener_por_id(comando.trabajo_id)
            if existente:
                # Idempotencia (GT-4): la reentrega del mismo trabajo_id no crea
                # un segundo trabajo ni vuelve a publicar TrabajoCreado.
                return str(existente.id)

        trabajo_dto = TrabajoDTO(
            id=comando.trabajo_id,
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
            simular_fallo=comando.simular_fallo,
        )
        # Saga (D2 de research.md): la transición CREADO→EMPAREJANDO la dispara
        # el propio handler, en el mismo commit, para que `evt-trabajo` porte el
        # estado correcto desde el primer momento en que Emparejamiento lo lee.
        trabajo.cambiar_estado(Estado.EMPAREJANDO, simular_fallo=comando.simular_fallo)

        repositorio = self.fabrica_repositorio.crear_objeto(RepositorioTrabajos)

        UnidadTrabajoPuerto.registrar_batch(repositorio.agregar, trabajo)
        UnidadTrabajoPuerto.commit()

        return str(trabajo.id)


@ejecutar_comando.register(CrearTrabajo)
def ejecutar_comando_crear_trabajo(comando: CrearTrabajo):
    return CrearTrabajoHandler().handle(comando)
