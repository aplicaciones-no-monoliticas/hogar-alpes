"""Repositorio de sagas — la única pieza de infraestructura con lógica: dedupe
por `mensaje_id` (CA-1.14, FR-016) y la tabla de derivación de estado (D9 de
research.md). `saga_log` no tiene agregación de dominio: es un observador puro
sobre lo que los otros tres servicios ya publicaron.
"""
import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from saga_log.config.db import db

from . import dto as modelo

AVANCE = 'AVANCE'
REVERSION = 'REVERSION'

# Tabla de mapeo fija `type` -> dirección (D2/D9): nunca persistida como
# configuración, es parte del código porque describe la forma de los
# contratos, no un dato que varíe en tiempo de ejecución.
_DIRECCION_POR_TIPO = {
    'hogaralpes.trabajo.creado.v1': AVANCE,
    # estado-cambiado se resuelve aparte, según el `estado` que trae el mensaje.
    'hogaralpes.emparejamiento.candidatos-identificados.v1': AVANCE,
    'hogaralpes.emparejamiento.sin-candidatos.v1': AVANCE,
    'hogaralpes.emparejamiento.proveedor-propuesto.v1': AVANCE,
    'hogaralpes.emparejamiento.candidatos-liberados.v1': REVERSION,
    'hogaralpes.acreditacion.vigencia-confirmada.v1': AVANCE,
    'hogaralpes.acreditacion.vigencia-rechazada.v1': REVERSION,
}

TIPO_ESTADO_CAMBIADO = 'hogaralpes.trabajo.estado-cambiado.v1'

# D9: qué paso produce qué estado de la TRANSACCIÓN. `None` = no cambia el
# estado actual (el paso solo se registra en la línea de tiempo).
_ESTADO_POR_TIPO = {
    'hogaralpes.trabajo.creado.v1': 'EN_CURSO',
    'hogaralpes.emparejamiento.sin-candidatos.v1': 'COMPENSADA',
    'hogaralpes.emparejamiento.candidatos-liberados.v1': 'COMPENSANDO',
    'hogaralpes.acreditacion.vigencia-rechazada.v1': 'COMPENSANDO',
}
_ESTADOS_FINALES = {'COMPLETADA', 'COMPENSADA'}


def direccion_de(tipo: str, estado_mensaje: str = '') -> str:
    if tipo == TIPO_ESTADO_CAMBIADO:
        return REVERSION if estado_mensaje == 'CANCELADO' else AVANCE
    return _DIRECCION_POR_TIPO.get(tipo, AVANCE)


def _estado_resultante(tipo: str, estado_mensaje: str = '') -> str | None:
    if tipo == TIPO_ESTADO_CAMBIADO:
        if estado_mensaje == 'ASIGNADO':
            return 'COMPLETADA'
        if estado_mensaje == 'CANCELADO':
            return 'COMPENSADA'
        return 'EN_CURSO'  # EMPAREJANDO
    return _ESTADO_POR_TIPO.get(tipo)


class RepositorioSagas:
    def registrar_paso(self, mensaje_id: str, trabajo_id: str, correlation_id: str,
                        servicio: str, tipo: str, ocurrido_en: datetime,
                        estado_mensaje: str = ''):
        """Idempotente: un `mensaje_id` repetido (reentrega) es un no-op —
        no duplica el paso ni vuelve a mover el estado de la transacción."""
        if not trabajo_id:
            return

        db.session.add(modelo.PasoSaga(
            id=str(uuid.uuid4()), mensaje_id=mensaje_id, trabajo_id=trabajo_id,
            correlation_id=correlation_id, servicio=servicio, paso=tipo,
            direccion=direccion_de(tipo, estado_mensaje), ocurrido_en=ocurrido_en,
        ))
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            return

        transaccion = (
            db.session.query(modelo.TransaccionSaga).filter_by(trabajo_id=trabajo_id).one_or_none()
        )
        if transaccion is None:
            transaccion = modelo.TransaccionSaga(
                trabajo_id=trabajo_id, correlation_id=correlation_id,
                estado='EN_CURSO', iniciada_en=ocurrido_en,
            )
            db.session.add(transaccion)

        nuevo_estado = _estado_resultante(tipo, estado_mensaje)
        if nuevo_estado and transaccion.estado not in _ESTADOS_FINALES:
            transaccion.estado = nuevo_estado
            if nuevo_estado in _ESTADOS_FINALES:
                transaccion.terminada_en = ocurrido_en
        db.session.commit()

    def obtener_transaccion(self, trabajo_id: str) -> modelo.TransaccionSaga | None:
        return (
            db.session.query(modelo.TransaccionSaga).filter_by(trabajo_id=trabajo_id).one_or_none()
        )

    def obtener_pasos(self, trabajo_id: str) -> list[modelo.PasoSaga]:
        return (
            db.session.query(modelo.PasoSaga)
            .filter_by(trabajo_id=trabajo_id)
            .order_by(modelo.PasoSaga.ocurrido_en)
            .all()
        )

    def obtener_por_estado(self, estado: str) -> list[modelo.TransaccionSaga]:
        return db.session.query(modelo.TransaccionSaga).filter_by(estado=estado).all()

    def obtener_incompletas(self, umbral_segundos: int) -> list[modelo.TransaccionSaga]:
        """D9: `INCOMPLETA` no se persiste — es una vista calculada sobre las
        filas todavía en `EN_CURSO`/`COMPENSANDO` con más antigüedad que el
        umbral configurado."""
        limite = datetime.utcnow() - timedelta(seconds=umbral_segundos)
        return (
            db.session.query(modelo.TransaccionSaga)
            .filter(modelo.TransaccionSaga.estado.in_(('EN_CURSO', 'COMPENSANDO')))
            .filter(modelo.TransaccionSaga.iniciada_en < limite)
            .all()
        )

    def contar_por_estado(self) -> dict[str, int]:
        filas = (
            db.session.query(modelo.TransaccionSaga.estado, db.func.count())
            .group_by(modelo.TransaccionSaga.estado)
            .all()
        )
        return {estado: total for estado, total in filas}
