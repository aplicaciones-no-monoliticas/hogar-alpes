"""Mapeadores de infraestructura:

- `MapeadorEventoAcreditacion`  — evento de dominio  <-> fila del event store.
- `MapeadorAcreditacionIntegracion` — evento de dominio -> esquema Avro
  `AcreditacionActualizada` (carga de estado, `evt-acreditacion`).
- `MapeadorAcreditacionExterno` — agregación -> `dict` para las respuestas HTTP.
"""
from acreditacion.seedwork.infraestructura import correlacion
from acreditacion.seedwork.infraestructura.schema.v1.mensajes import sobre

from ..dominio.entidades import Acreditacion
from ..dominio.eventos import TIPOS_EVENTO
from .schema.v1.eventos import (
    TIPO_ACTUALIZADA,
    TIPO_VIGENCIA_CONFIRMADA,
    TIPO_VIGENCIA_RECHAZADA,
    AcreditacionActualizada,
)

CAMPOS_EVENTO = (
    'proveedor_id', 'pais', 'ciudad', 'categorias', 'nivel', 'vigencia_meses',
    'estado', 'vigente_hasta', 'motivo',
)


class MapeadorEventoAcreditacion:
    def evento_a_datos(self, evento) -> dict:
        """Solo la carga: `agregado_id`, `version` y `tipo` ya tienen su propia
        columna en la fila, y `id`/`fecha_evento` no aportan a la reproducción."""
        return {campo: getattr(evento, campo) for campo in CAMPOS_EVENTO}

    def datos_a_evento(self, tipo: str, datos: dict, agregado_id, version: int, ocurrido_en):
        cls = TIPOS_EVENTO[tipo]
        return cls(
            agregado_id=agregado_id, version=version, fecha_evento=ocurrido_en,
            **{campo: datos.get(campo) for campo in CAMPOS_EVENTO},
        )


class MapeadorAcreditacionIntegracion:
    """Lo que consume el `Despachador` de la plantilla: `entidad_a_dto(evento)`
    devuelve `(mensaje, schema)`, no un DTO simple (ver `despachadores.py`)."""

    def entidad_a_dto(self, evento):
        mensaje = AcreditacionActualizada(
            **sobre(TIPO_ACTUALIZADA, 'acreditacion', correlation_id=correlacion.actual()),
            acreditacion_id=str(evento.agregado_id),
            proveedor_id=evento.proveedor_id,
            pais=evento.pais,
            ciudad=evento.ciudad,
            categorias=list(evento.categorias),
            nivel=evento.nivel,
            estado=evento.estado,
            vigente_hasta=evento.vigente_hasta,
            version=evento.version,
            # D8 de research.md: vacío en el snapshot — no pertenece a
            # ninguna saga.
            trabajo_id='',
            categoria='',
        )
        return mensaje, AcreditacionActualizada


class MapeadorVigenciaIntegracion:
    """Saga (Entrega 5, D2/D8): a diferencia de `MapeadorAcreditacionIntegracion`,
    no traduce un evento de dominio del agregado —no hay mutación del event
    store en este paso—, sino el resultado (`DecisionVigencia`) de haber
    consultado la proyección `vigencia_por_proveedor`. Misma interfaz que
    consume el `Despachador`: `entidad_a_dto(evento)` -> `(mensaje, schema)`."""

    def entidad_a_dto(self, decision):
        tipo = TIPO_VIGENCIA_CONFIRMADA if decision.confirmada else TIPO_VIGENCIA_RECHAZADA
        mensaje = AcreditacionActualizada(
            **sobre(tipo, 'acreditacion', correlation_id=correlacion.actual()),
            acreditacion_id='',
            proveedor_id=decision.proveedor_id,
            pais='',
            ciudad='',
            categorias=[],
            nivel='',
            estado='',
            vigente_hasta='',
            version=0,
            trabajo_id=decision.trabajo_id,
            categoria=decision.categoria,
        )
        return mensaje, AcreditacionActualizada


class MapeadorAcreditacionExterno:
    def entidad_a_externo(self, acreditacion: Acreditacion) -> dict:
        return {
            'id': str(acreditacion.id),
            'proveedor_id': acreditacion.proveedor_id,
            'pais': acreditacion.pais,
            'ciudad': acreditacion.ciudad,
            'categorias': list(acreditacion.categorias),
            'nivel': acreditacion.nivel,
            'estado': acreditacion.estado.valor.value,
            'vigente_hasta': acreditacion.vigente_hasta,
            'version': acreditacion.version,
        }
