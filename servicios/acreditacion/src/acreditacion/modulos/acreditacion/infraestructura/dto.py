"""Modelo de persistencia del event store: `eventos_acreditacion`, append-only.

`UNIQUE(agregado_id, version)` es el control de concurrencia optimista (ACR-2):
dos escrituras concurrentes que parten del mismo estado calculan la misma
versión siguiente, y el índice único deja pasar solo a la primera.
"""
from sqlalchemy import Column, DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class EventoAcreditacion(Base):
    __tablename__ = 'eventos_acreditacion'
    __table_args__ = (
        UniqueConstraint('agregado_id', 'version', name='uq_evento_acreditacion_agregado_version'),
    )

    id = Column(String(40), primary_key=True)
    agregado_id = Column(String(40), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    tipo = Column(String(60), nullable=False)
    datos = Column(JSON, nullable=False)
    ocurrido_en = Column(DateTime, nullable=False)


class VigenciaPorProveedor(Base):
    """Saga (Entrega 5, D4 de research.md): proyección de lectura interna,
    propia de Acreditación — no es la del event store ni la de Emparejamiento.
    Se actualiza junto con cada evento que ya se escribe en
    `eventos_acreditacion` (mismo `agregar`, misma transacción)."""
    __tablename__ = 'vigencia_por_proveedor'

    proveedor_id = Column(String(40), primary_key=True)
    categoria = Column(String(40), primary_key=True)
    estado = Column(String(20), nullable=False)
    vigente_hasta = Column(String(10), nullable=False)  # ISO-8601, comparable como texto
    version = Column(Integer, nullable=False)
