"""Handler de eventos de INTEGRACIÓN del módulo acreditación.

Escucha la señal que la Unidad de Trabajo emite DESPUÉS del commit y publica el
snapshot completo en `evt-acreditacion`. Los tres eventos de dominio
—Solicitada, Aprobada, Revocada— ya llevan el estado completo del agregado
(ver `dominio/eventos.py`), así que no hace falta releer nada: se traduce
campo a campo con `MapeadorAcreditacionIntegracion`.

Es el único punto del módulo que sabe que existe un broker.
"""
from pydispatch import dispatcher

from acreditacion.config.topicos import topico_evt_acreditacion
from acreditacion.seedwork.aplicacion.handlers import Handler
from acreditacion.seedwork.infraestructura.despachadores import Despachador

from ..infraestructura.mapeadores import MapeadorAcreditacionIntegracion


class HandlerAcreditacionIntegracion(Handler):
    @staticmethod
    def publicar(evento):
        Despachador().publicar_evento(
            evento,
            topico_evt_acreditacion(),
            MapeadorAcreditacionIntegracion(),
            clave=evento.proveedor_id,
            propiedades={'correlation_id': evento.proveedor_id},
        )


for _senal in ('AcreditacionSolicitadaIntegracion', 'AcreditacionAprobadaIntegracion',
               'AcreditacionRevocadaIntegracion'):
    dispatcher.connect(HandlerAcreditacionIntegracion.publicar, signal=_senal)
