"""CON-1 · Verificación de los cinco contratos contra el clúster.

Comprueba tres cosas por contrato. Las tres nacieron de un defecto real, no de
una idea de completitud:

1. **Todos los campos llevan `"default"`** (regla de INF-0). Sin eso el broker
   rechaza la primera evolución que agregue un campo.
2. **El sobre está presente**, los ocho campos. La herencia de `Record` pierde
   los campos del padre en silencio, y así fue como el servicio Gestión de
   Trabajos terminó publicando eventos sin sobre (ver `contratos/v1/mensajes.py`).
3. **El mensaje viaja de ida y vuelta con sus valores.** La comparación es
   contra **literales**, no contra los atributos del objeto publicado: un campo
   que no se deserializa devuelve el descriptor de clase, y comparar dos
   descriptores da `True` sin probar nada. La primera versión de este script
   cayó justo en esa trampa.

Usa el namespace de experimentos `public/default` con tópicos temporales, así no
depende de INF-3.

    python herramientas/verificar_contratos.py
"""
import os
import sys
import time
import uuid

import pulsar
from pulsar.schema import AvroSchema

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from contratos.v1.cmd_acreditacion import SOLICITAR, ComandoAcreditacion  # noqa: E402
from contratos.v1.cmd_trabajo import TIPO_CREAR, ComandoCrearTrabajo  # noqa: E402
from contratos.v1.evt_acreditacion import TIPO_ACTUALIZADA, AcreditacionActualizada  # noqa: E402
from contratos.v1.evt_emparejamiento import TIPO_CANDIDATOS, EventoEmparejamiento  # noqa: E402
from contratos.v1.evt_trabajo import TIPO_CREADO, EventoTrabajo  # noqa: E402
from contratos.v1.mensajes import CAMPOS_SOBRE, sobre  # noqa: E402

SERVICIO = os.getenv('BROKER_URL', 'pulsar://localhost:6650')
# Desde el host hay que pedir el listener externo (INF-2 en docs/decisiones.md).
LISTENER = os.getenv('BROKER_LISTENER', 'external')
SUFIJO = int(time.time())

fallos = []


def verificar(nombre, cls, valores, clave, esperado: dict):
    """`esperado` son literales: {campo: valor} que deben volver intactos."""
    print(f'\n--- {nombre}')
    campos = {c['name'] for c in cls.schema()['fields']}

    sin_default = [c['name'] for c in cls.schema()['fields'] if 'default' not in c]
    if sin_default:
        fallos.append(f'{nombre}: campos sin default {sin_default}')
        print(f'    FALLA · campos sin "default": {sin_default}')
    else:
        print(f'    regla de INF-0 · los {len(campos)} campos llevan "default"')

    faltan = [c for c in CAMPOS_SOBRE if c not in campos]
    if faltan:
        fallos.append(f'{nombre}: sobre incompleto {faltan}')
        print(f'    FALLA · faltan campos del sobre: {faltan}')
    else:
        print('    sobre completo · los 8 campos presentes')

    topico = f'persistent://public/default/con1-{nombre}-{SUFIJO}'
    cliente = pulsar.Client(SERVICIO, listener_name=LISTENER, operation_timeout_seconds=15)
    try:
        consumidor = cliente.subscribe(
            topico, 'verificador', schema=AvroSchema(cls),
            initial_position=pulsar.InitialPosition.Earliest,
        )
        productor = cliente.create_producer(topico, schema=AvroSchema(cls))
        productor.send(cls(**valores), partition_key=clave)

        mensaje = consumidor.receive(timeout_millis=10000)
        leido = mensaje.value()
        consumidor.acknowledge(mensaje)

        diferencias = {
            campo: (esperado[campo], getattr(leido, campo))
            for campo in esperado
            if getattr(leido, campo) != esperado[campo]
        }
        if diferencias:
            fallos.append(f'{nombre}: no coincide {list(diferencias)}')
            print(f'    FALLA · campos que no volvieron intactos: {diferencias}')
        else:
            print(f'    ida y vuelta · {len(esperado)} campos intactos · clave={clave}')
            print(f'    type={leido.type} · correlation_id={leido.correlation_id}')
    except Exception as e:
        fallos.append(f'{nombre}: {type(e).__name__}')
        print(f'    FALLA · {type(e).__name__}: {e}')
    finally:
        cliente.close()


def main():
    trabajo_id = str(uuid.uuid4())
    proveedor_id = str(uuid.uuid4())
    acreditacion_id = str(uuid.uuid4())

    v = dict(sobre(TIPO_CREAR, 'verificador', correlation_id=trabajo_id),
             trabajo_id=trabajo_id, canal='B2B2C', partner_id='seguros-alpes',
             referencia_externa='SIN-1', categoria='SINIESTRO_GRANIZO',
             urgencia='CRITICA', pais='CO', ciudad='Bogota',
             direccion='Cra 7 # 71-21', descripcion='granizada')
    verificar('cmd-trabajo', ComandoCrearTrabajo, v, trabajo_id,
              {'type': TIPO_CREAR, 'correlation_id': trabajo_id,
               'trabajo_id': trabajo_id, 'categoria': 'SINIESTRO_GRANIZO',
               'service_name': 'verificador'})

    v = dict(sobre(TIPO_CREADO, 'verificador', correlation_id=trabajo_id),
             trabajo_id=trabajo_id, partner_id='seguros-alpes', canal='B2B2C',
             pais='CO', ciudad='Bogota', categoria='SINIESTRO_GRANIZO',
             urgencia='CRITICA', estado='CREADO', estado_anterior='')
    verificar('evt-trabajo', EventoTrabajo, v, trabajo_id,
              {'type': TIPO_CREADO, 'correlation_id': trabajo_id,
               'trabajo_id': trabajo_id, 'estado': 'CREADO'})

    v = dict(sobre('hogaralpes.acreditacion.solicitar.v1', 'verificador',
                   correlation_id=proveedor_id),
             tipo_comando=SOLICITAR, acreditacion_id=acreditacion_id,
             proveedor_id=proveedor_id, pais='CO', ciudad='Bogota',
             categorias=['PLOMERIA', 'GAS'], nivel='ORO', vigencia_meses=12,
             motivo='')
    verificar('cmd-acreditacion', ComandoAcreditacion, v, proveedor_id,
              {'tipo_comando': SOLICITAR, 'proveedor_id': proveedor_id,
               'categorias': ['PLOMERIA', 'GAS'], 'vigencia_meses': 12})

    v = dict(sobre(TIPO_ACTUALIZADA, 'verificador', correlation_id=proveedor_id),
             acreditacion_id=acreditacion_id, proveedor_id=proveedor_id,
             pais='CO', ciudad='Bogota', categorias=['PLOMERIA', 'GAS'],
             nivel='ORO', estado='ACREDITADA', vigente_hasta='2027-09-11',
             version=2)
    verificar('evt-acreditacion', AcreditacionActualizada, v, proveedor_id,
              {'estado': 'ACREDITADA', 'version': 2,
               'categorias': ['PLOMERIA', 'GAS'], 'proveedor_id': proveedor_id})

    candidatos = [str(uuid.uuid4()) for _ in range(3)]
    v = dict(sobre(TIPO_CANDIDATOS, 'verificador', correlation_id=trabajo_id),
             trabajo_id=trabajo_id, region='andina',
             categoria='SINIESTRO_GRANIZO', pais='CO', ciudad='Bogota',
             total_candidatos=3, candidatos=candidatos)
    verificar('evt-emparejamiento', EventoEmparejamiento, v, trabajo_id,
              {'trabajo_id': trabajo_id, 'region': 'andina',
               'total_candidatos': 3, 'candidatos': candidatos})

    print('\n' + '=' * 70)
    if fallos:
        print('FALLA · ' + ' | '.join(fallos))
        raise SystemExit(1)
    print('PASA · los 5 contratos llevan sobre completo, cumplen la regla de '
          'INF-0 y viajan de ida y vuelta con sus valores')


if __name__ == '__main__':
    main()
