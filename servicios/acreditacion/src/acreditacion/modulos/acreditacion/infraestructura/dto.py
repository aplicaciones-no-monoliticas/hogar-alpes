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
