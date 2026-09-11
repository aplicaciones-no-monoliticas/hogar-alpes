from sqlalchemy import Column, DateTime, Integer, String

from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Seguimiento(Base):
    __tablename__ = 'seguimientos_operativos'

    id = Column(String(40), primary_key=True)
    trabajo_id = Column(String(40), nullable=False, index=True)
    pais = Column(String(4), nullable=False)
    canal = Column(String(20), nullable=False)
    categoria = Column(String(40), nullable=False)
    estado_trabajo = Column(String(30), nullable=False)
    prioridad = Column(String(4), nullable=False)
    minutos_sla = Column(Integer, nullable=False)
    fecha_creacion = Column(DateTime, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)
