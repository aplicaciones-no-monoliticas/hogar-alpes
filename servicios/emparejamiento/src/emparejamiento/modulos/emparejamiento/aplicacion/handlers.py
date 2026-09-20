"""Handler de eventos de INTEGRACIÓN del módulo emparejamiento.

Escucha la señal que la Unidad de Trabajo emite DESPUÉS del commit y publica en
`evt-emparejamiento`. Nadie lo consume todavía en la Entrega 4 (§4.3 de la
especificación): se publica igual porque es el paso 2 de la transacción larga
de referencia, y lo escuchará la saga de la Entrega 5.
"""
from pydispatch import dispatcher

from emparejamiento.config.topicos import topico_evt_emparejamiento
from emparejamiento.seedwork.aplicacion.handlers import Handler
from emparejamiento.seedwork.infraestructura.despachadores import Despachador

from ..infraestructura.mapeadores import MapeadorEmparejamientoIntegracion


class HandlerEmparejamientoIntegracion(Handler):
    @staticmethod
    def publicar(evento):
        propiedades = {'region': evento.region}
        # Marca de demostración de la saga (D3 de research.md): nunca es parte
        # del esquema Avro, solo viaja como propiedad, y solo si la trajo el
        # productor original.
        simular_fallo = getattr(evento, 'simular_fallo', '')
        if simular_fallo:
            propiedades['simular_fallo'] = simular_fallo
        Despachador().publicar_evento(
            evento,
            topico_evt_emparejamiento(),
            MapeadorEmparejamientoIntegracion(),
            clave=str(evento.trabajo_id),
            propiedades=propiedades,
        )


for _senal in (
    'CandidatosIdentificadosIntegracion', 'SinCandidatosIntegracion',
    'ProveedorPropuestoIntegracion', 'CandidatosLiberadosIntegracion',
):
    dispatcher.connect(HandlerEmparejamientoIntegracion.publicar, signal=_senal)
