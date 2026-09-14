"""Modelos de persistencia (SQLAlchemy) — dos tablas (§4.2 y §7 de la
especificación):

- `seguimientos_operativos`: el lado de escritura, uno por trabajo
  (`UNIQUE(trabajo_id)`).
- `eventos_procesados`: idempotencia del consumidor. `evento_id` como clave
  primaria — reentregar el mismo mensaje no duplica nada — con `resultado`
  para distinguir APLICADO de DUPLICADO y de HUERFANO (CA-6.4, CA-6.5).
"""
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Seguimiento(Base):
    __tablename__ = 'seguimientos_operativos'

    id = Column(String(40), primary_key=True)
    trabajo_id = Column(String(40), nullable=False, unique=True, index=True)
    pais = Column(String(4), nullable=False)
    canal = Column(String(20), nullable=False)
    categoria = Column(String(40), nullable=False)
    estado_trabajo = Column(String(30), nullable=False)
    prioridad = Column(String(4), nullable=False)
    minutos_sla = Column(Integer, nullable=False)
    fecha_creacion = Column(DateTime, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)


class EventoProcesado(Base):
    __tablename__ = 'eventos_procesados'

    evento_id = Column(String(64), primary_key=True)
    tipo = Column(String(80), nullable=False)
    resultado = Column(String(10), nullable=False)  # APLICADO | DUPLICADO | HUERFANO
    fecha = Column(DateTime, nullable=False)
