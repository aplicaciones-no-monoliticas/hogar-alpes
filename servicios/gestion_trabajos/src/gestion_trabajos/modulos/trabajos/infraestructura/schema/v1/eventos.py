"""Contrato PÚBLICO del servicio, versionado en `v1`.

Los consumidores externos dependen de esto, no del modelo de dominio. Un cambio
incompatible se publica como `v2` y `v1` sigue vivo: es lo que permite que un
consumidor que aún no conoce un estado nuevo lo ignore sin romperse (tolerant
reader, escenario 3).
"""
from pulsar.schema import Record, String

from gestion_trabajos.seedwork.infraestructura.schema.v1.mensajes import (
    EventoIntegracion,
)


class TrabajoCreadoPayload(Record):
    trabajo_id = String()
    categoria = String()
    urgencia = String()
    pais = String()
    ciudad = String()
    canal = String()
    partner_id = String()
    estado = String()


class EventoTrabajoCreado(EventoIntegracion):
    data = TrabajoCreadoPayload()


class EstadoTrabajoCambiadoPayload(Record):
    trabajo_id = String()
    estado_anterior = String()
    estado_nuevo = String()


class EventoEstadoTrabajoCambiado(EventoIntegracion):
    data = EstadoTrabajoCambiadoPayload()
