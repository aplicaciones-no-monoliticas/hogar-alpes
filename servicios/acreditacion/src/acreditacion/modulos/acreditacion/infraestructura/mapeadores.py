"""Mapeadores de infraestructura:

- `MapeadorEventoAcreditacion`  — evento de dominio  <-> fila del event store.
- `MapeadorAcreditacionIntegracion` — evento de dominio -> esquema Avro
  `AcreditacionActualizada` (carga de estado, `evt-acreditacion`).
- `MapeadorAcreditacionExterno` — agregación -> `dict` para las respuestas HTTP.
"""
from acreditacion.seedwork.infraestructura.schema.v1.mensajes import sobre

from ..dominio.entidades import Acreditacion
from ..dominio.eventos import TIPOS_EVENTO
from .schema.v1.eventos import TIPO_ACTUALIZADA, AcreditacionActualizada

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
            **sobre(TIPO_ACTUALIZADA, 'acreditacion', correlation_id=evento.proveedor_id),
            acreditacion_id=str(evento.agregado_id),
            proveedor_id=evento.proveedor_id,
            pais=evento.pais,
            ciudad=evento.ciudad,
            categorias=list(evento.categorias),
            nivel=evento.nivel,
            estado=evento.estado,
            vigente_hasta=evento.vigente_hasta,
            version=evento.version,
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
