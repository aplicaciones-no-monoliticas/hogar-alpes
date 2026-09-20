"""ADAPTADOR de Event Sourcing sobre PostgreSQL.

`obtener_por_id` no lee una fila: reproduce el log completo del agregado,
evento a evento, con `Acreditacion.aplicar_evento` — la misma mutación que se
usó para llegar a ese estado la primera vez.

`agregar` no reemplaza nada: **añade** las filas de los eventos que el agregado
tiene pendientes (`acreditacion.eventos`, los que dejó el último comando).
`db.session.flush()` fuerza el `INSERT` de inmediato para que el conflicto de
`UNIQUE(agregado_id, version)` —dos comandos concurrentes calculando la misma
versión siguiente— se detecte aquí y no en un commit posterior más difícil de
atribuir.
"""
import uuid

from sqlalchemy.exc import IntegrityError

from acreditacion.config.db import db

from ..dominio.entidades import Acreditacion
from ..dominio.excepciones import ConflictoDeConcurrenciaExcepcion
from ..dominio.repositorios import RepositorioAcreditaciones, RepositorioVigenciaPorProveedor
from . import dto as modelo
from .mapeadores import MapeadorEventoAcreditacion


class RepositorioAcreditacionesEventSourcing(RepositorioAcreditaciones):
    def __init__(self):
        self._mapeador = MapeadorEventoAcreditacion()

    def obtener_por_id(self, id) -> Acreditacion | None:
        filas = (
            db.session.query(modelo.EventoAcreditacion)
            .filter_by(agregado_id=str(id))
            .order_by(modelo.EventoAcreditacion.version)
            .all()
        )
        if not filas:
            return None

        acreditacion = Acreditacion(id=uuid.UUID(str(id)))
        for fila in filas:
            evento = self._mapeador.datos_a_evento(
                fila.tipo, fila.datos, acreditacion.id, fila.version, fila.ocurrido_en
            )
            acreditacion.aplicar_evento(evento)
        # Los eventos reproducidos ya están persistidos: no son un pendiente de
        # publicación nuevo. Sin este `limpiar_eventos`, un `aprobar()` sobre un
        # agregado recién cargado republicaría también la solicitud original.
        acreditacion.limpiar_eventos()
        return acreditacion

    def agregar(self, acreditacion: Acreditacion):
        if not acreditacion.eventos:
            return
        for evento in acreditacion.eventos:
            db.session.add(
                modelo.EventoAcreditacion(
                    id=str(uuid.uuid4()),
                    agregado_id=str(evento.agregado_id),
                    version=evento.version,
                    tipo=type(evento).__name__,
                    datos=self._mapeador.evento_a_datos(evento),
                    ocurrido_en=evento.fecha_evento,
                )
            )
        try:
            db.session.flush()
        except IntegrityError as e:
            db.session.rollback()
            raise ConflictoDeConcurrenciaExcepcion() from e

        # D4/D27 (saga, Entrega 5): la proyección `vigencia_por_proveedor` se
        # actualiza en la MISMA transacción que el event store, no en un
        # consumidor aparte — es una escritura adicional, no un paso nuevo.
        repo_vigencia = RepositorioVigenciaPorProveedorPostgres()
        for evento in acreditacion.eventos:
            for categoria in evento.categorias:
                repo_vigencia.upsert(
                    proveedor_id=evento.proveedor_id, categoria=categoria,
                    estado=evento.estado, vigente_hasta=evento.vigente_hasta,
                    version=evento.version,
                )

    def historial(self, id) -> list[dict]:
        filas = (
            db.session.query(modelo.EventoAcreditacion)
            .filter_by(agregado_id=str(id))
            .order_by(modelo.EventoAcreditacion.version)
            .all()
        )
        return [
            {
                'version': f.version,
                'tipo': f.tipo,
                'datos': f.datos,
                'ocurrido_en': f.ocurrido_en.isoformat(),
            }
            for f in filas
        ]


class RepositorioVigenciaPorProveedorPostgres(RepositorioVigenciaPorProveedor):
    def consultar(self, proveedor_id: str, categoria: str) -> dict | None:
        registro = (
            db.session.query(modelo.VigenciaPorProveedor)
            .filter_by(proveedor_id=proveedor_id, categoria=categoria)
            .one_or_none()
        )
        if not registro:
            return None
        return {
            'estado': registro.estado, 'vigente_hasta': registro.vigente_hasta,
            'version': registro.version,
        }

    def upsert(self, proveedor_id: str, categoria: str, estado: str,
               vigente_hasta: str, version: int):
        registro = (
            db.session.query(modelo.VigenciaPorProveedor)
            .filter_by(proveedor_id=proveedor_id, categoria=categoria)
            .one_or_none()
        )
        if registro is None:
            db.session.add(modelo.VigenciaPorProveedor(
                proveedor_id=proveedor_id, categoria=categoria, estado=estado,
                vigente_hasta=vigente_hasta, version=version,
            ))
            return

        if version <= registro.version:
            # Tolerante al desorden: un evento viejo llegado tarde no pisa uno
            # más nuevo que ya se aplicó.
            return

        registro.estado = estado
        registro.vigente_hasta = vigente_hasta
        registro.version = version
