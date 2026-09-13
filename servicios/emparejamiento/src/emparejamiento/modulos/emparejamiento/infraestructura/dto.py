"""Modelos de persistencia (SQLAlchemy) — dos tablas, dos modelos (§7 y §4 de
la especificación):

- `proveedores_candidatos`: la PROYECCIÓN de lectura, alimentada solo por
  `evt-acreditacion`. Clave primaria compuesta (`proveedor_id`, `categoria`):
  un proveedor puede estar acreditado en más de una categoría, y cada una
  evoluciona con su propia `version`. El índice parcial es la optimización
  del escenario 8 — la consulta de candidatos SIEMPRE filtra por
  `estado='ACREDITADA'`, así que es la única condición que vale la pena
  indexar aparte.
- `emparejamientos`: el lado de escritura de la agregación, uno por trabajo.
"""
from sqlalchemy import Column, Index, Integer, JSON, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ProveedorCandidato(Base):
    __tablename__ = 'proveedores_candidatos'

    proveedor_id = Column(String(40), primary_key=True)
    categoria = Column(String(40), primary_key=True)
    pais = Column(String(4), nullable=False)
    ciudad = Column(String(80), nullable=False)
    nivel = Column(String(40), nullable=False)
    estado = Column(String(20), nullable=False)
    vigente_hasta = Column(String(10), nullable=False)  # ISO-8601, comparable como texto
    version = Column(Integer, nullable=False)

    __table_args__ = (
        Index(
            'ix_proveedores_candidatos_busqueda',
            'pais', 'ciudad', 'categoria',
            postgresql_where=(estado == 'ACREDITADA'),
        ),
    )


class Emparejamiento(Base):
    __tablename__ = 'emparejamientos'

    trabajo_id = Column(String(40), primary_key=True)
    region = Column(String(40), nullable=False)
    categoria = Column(String(40), nullable=False)
    pais = Column(String(4), nullable=False)
    ciudad = Column(String(80), nullable=False)
    candidatos = Column(JSON, nullable=False)  # lista de proveedor_id
    total = Column(Integer, nullable=False)
