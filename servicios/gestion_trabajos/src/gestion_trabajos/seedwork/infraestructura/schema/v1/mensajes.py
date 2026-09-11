"""Envolvente estándar de los mensajes que salen del servicio.

Sigue la definición de CloudEvents. El paquete `v1` es el versionamiento: una
versión incompatible del contrato vive en `v2`, sin romper a los consumidores
que siguen leyendo `v1` (contratos y evolución de esquemas, semana 4).
"""
from pulsar.schema import Record, String, Long


class Mensaje(Record):
    id = String()
    time = Long()
    specversion = String()
    type = String()
    ingestion = Long()
    datacontenttype = String()
    service_name = String()


class EventoIntegracion(Mensaje):
    ...


class ComandoIntegracion(Mensaje):
    ...
