from pulsar.schema import Record, String

from gestion_trabajos.seedwork.infraestructura.schema.v1.mensajes import (
    ComandoIntegracion,
)


class CrearTrabajoPayload(Record):
    canal = String()
    partner_id = String()
    referencia_externa = String()
    categoria = String()
    urgencia = String()
    pais = String()
    ciudad = String()
    direccion = String()
    descripcion = String()


class ComandoCrearTrabajo(ComandoIntegracion):
    data = CrearTrabajoPayload()
