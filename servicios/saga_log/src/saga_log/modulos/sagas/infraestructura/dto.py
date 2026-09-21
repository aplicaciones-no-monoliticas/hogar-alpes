"""Modelos de persistencia (SQLAlchemy). `saga_log` es de solo lectura sobre lo
que observa: no hay una capa de dominio con reglas de negocio que proteger,
más allá de la deduplicación (D9 de research.md), así que estas tablas SON el
modelo de persistencia — no hay agregación ni Event Sourcing detrás.
"""
from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TransaccionSaga(Base):
    __tablename__ = 'transacciones_saga'

    trabajo_id = Column(String(40), primary_key=True)
    correlation_id = Column(String(64), nullable=False, index=True)
    # EN_CURSO · COMPLETADA · COMPENSANDO · COMPENSADA (INCOMPLETA es calculada)
    estado = Column(String(20), nullable=False)
    iniciada_en = Column(DateTime, nullable=False)
    terminada_en = Column(DateTime, nullable=True)


class PasoSaga(Base):
    __tablename__ = 'pasos_saga'

    id = Column(String(40), primary_key=True)
    # Clave de deduplicación (CA-1.14): el campo `id` del sobre CloudEvents del
    # mensaje observado, único por mensaje publicado.
    mensaje_id = Column(String(40), nullable=False, unique=True)
    trabajo_id = Column(String(40), nullable=False, index=True)
    correlation_id = Column(String(64), nullable=False)
    # gestion-trabajos · emparejamiento · acreditacion
    servicio = Column(String(40), nullable=False)
    # El `type` del mensaje observado, tal cual.
    paso = Column(String(80), nullable=False)
    # AVANCE · REVERSION — derivado del `type` en el repositorio, no persistido
    # como configuración.
    direccion = Column(String(10), nullable=False)
    ocurrido_en = Column(DateTime, nullable=False)
