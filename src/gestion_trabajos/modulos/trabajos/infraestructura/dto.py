"""Modelos de persistencia (SQLAlchemy). Son de INFRAESTRUCTURA, no de dominio.

La agregación `Trabajo` no lleva una sola anotación de ORM: por eso cambiar de
motor de base de datos no la toca (escenario 1).
"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Trabajo(Base):
    __tablename__ = 'trabajos'

    id = Column(String(40), primary_key=True)
    fecha_creacion = Column(DateTime, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)
    canal = Column(String(20), nullable=False)
    partner_id = Column(String(60), nullable=True)
    referencia_externa = Column(String(120), nullable=True)
    categoria = Column(String(40), nullable=False)
    urgencia = Column(String(20), nullable=False)
    pais = Column(String(4), nullable=False, index=True)
    ciudad = Column(String(80), nullable=False)
    direccion = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    estado = Column(String(30), nullable=False, index=True)

    sub_trabajos = relationship(
        'SubTrabajo', cascade='all, delete-orphan', lazy='joined'
    )


class SubTrabajo(Base):
    __tablename__ = 'sub_trabajos'

    id = Column(String(40), primary_key=True)
    trabajo_id = Column(String(40), ForeignKey('trabajos.id'), nullable=False)
    descripcion = Column(Text, nullable=True)
    categoria = Column(String(40), nullable=False)
    estado = Column(String(30), nullable=False)
