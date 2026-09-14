#!/usr/bin/env python3
"""ESC-E · Escenario de esquemas — CA-E1 y CA-E2. Ver `docs/01-especificacion.md`
§6.2 y `docs/decisiones.md` (INF-0, CON-1).

A diferencia de `herramientas/spike_esquemas.py` (que responde preguntas
genéricas sobre el cliente), este script demuestra la evolución REAL del
contrato `ComandoCrearTrabajo` (`cmd-trabajo-*`, CON-1):

  CA-E1 · Agregar `trabajo_id` (el campo que GT-4 añadió, opcional con
          `default`) es aceptado por el registro, y un consumidor con la
          versión ANTERIOR (sin `trabajo_id`) sigue leyendo los mensajes
          nuevos sin error.
  CA-E2 · Publicar un cambio incompatible (`trabajo_id` de `String` a `Long`)
          en el mismo stream es RECHAZADO por el broker.

Corre contra `public/default` (creación automática de tópicos habilitada
ahí — ver INF-2 en `docs/decisiones.md`), no contra `cmd-trabajo-*` real: así
la corrida no deja esquemas de prueba en el historial del tópico de
producción, y se puede repetir tantas veces como haga falta.

Uso:
    python escenarios/esquemas.py
    python escenarios/esquemas.py --broker pulsar://localhost:6650 --listener external
"""
import argparse
import sys
import time

import pulsar
from pulsar.schema import AvroSchema, Long, Record, String

NOMBRE_CONTRATO = 'ComandoCrearTrabajo'


def _v1_sin_trabajo_id():
    """La forma del contrato ANTES de GT-4: sin `trabajo_id`. Representa al
    consumidor viejo — el que no sabe de este campo todavía."""
    class ComandoCrearTrabajo(Record):
        id = String(default=None, required_default=True)
        time = Long(default=None, required_default=True)
        ingestion = Long(default=None, required_default=True)
        specversion = String(default=None, required_default=True)
        type = String(default=None, required_default=True)
        datacontenttype = String(default=None, required_default=True)
        service_name = String(default=None, required_default=True)
        correlation_id = String(default=None, required_default=True)
        canal = String(default=None, required_default=True)
        partner_id = String(default=None, required_default=True)
        referencia_externa = String(default=None, required_default=True)
        categoria = String(default=None, required_default=True)
        urgencia = String(default=None, required_default=True)
        pais = String(default=None, required_default=True)
        ciudad = String(default=None, required_default=True)
        direccion = String(default=None, required_default=True)
        descripcion = String(default=None, required_default=True)
    return ComandoCrearTrabajo


def _v2_con_trabajo_id():
    """El contrato real de GT-4 / CON-1: `contratos/v1/cmd_trabajo.py`, con
    `trabajo_id`. Se importa el módulo real para no duplicar la definición —
    si alguien cambia el contrato, este script evoluciona con él."""
    sys.path.insert(0, __file__.rsplit('/escenarios/', 1)[0])
    from contratos.v1.cmd_trabajo import ComandoCrearTrabajo
    return ComandoCrearTrabajo


def _v2_incompatible():
    """Mismo nombre de contrato, `trabajo_id` cambia de tipo: String -> Long.
    Es el cambio que RS-4 dice que exige un stream nuevo (`-v2`), no una
    evolución en el mismo."""
    class ComandoCrearTrabajo(Record):
        id = String(default=None, required_default=True)
        time = Long(default=None, required_default=True)
        ingestion = Long(default=None, required_default=True)
        specversion = String(default=None, required_default=True)
        type = String(default=None, required_default=True)
        datacontenttype = String(default=None, required_default=True)
        service_name = String(default=None, required_default=True)
        correlation_id = String(default=None, required_default=True)
        trabajo_id = Long(default=0, required_default=True)  # <- era String
        canal = String(default=None, required_default=True)
        partner_id = String(default=None, required_default=True)
        referencia_externa = String(default=None, required_default=True)
        categoria = String(default=None, required_default=True)
        urgencia = String(default=None, required_default=True)
        pais = String(default=None, required_default=True)
        ciudad = String(default=None, required_default=True)
        direccion = String(default=None, required_default=True)
        descripcion = String(default=None, required_default=True)
    return ComandoCrearTrabajo


def _sobre():
    ahora = int(time.time() * 1000)
    return dict(
        id='esquemas-esc-e', time=ahora, ingestion=ahora, specversion='1.0',
        type='hogaralpes.trabajo.crear.v1', datacontenttype='application/avro',
        service_name='esquemas-esc-e', correlation_id='esquemas-esc-e',
    )


def _mensaje_v1(V1):
    return V1(**_sobre(), canal='MARKETPLACE', partner_id='p1', referencia_externa='r1',
              categoria='PLOMERIA', urgencia='NORMAL', pais='CO', ciudad='Bogota',
              direccion='Cra 7', descripcion='esquemas')


def _mensaje_v2(V2):
    return V2(**_sobre(), trabajo_id='11111111-1111-1111-1111-111111111111',
              canal='MARKETPLACE', partner_id='p1', referencia_externa='r1',
              categoria='PLOMERIA', urgencia='NORMAL', pais='CO', ciudad='Bogota',
              direccion='Cra 7', descripcion='esquemas')


def ca_e1(cliente, topico):
    print(f'\n=== CA-E1 · agregar trabajo_id (compatible) — {topico}')
    V1 = _v1_sin_trabajo_id()
    V2 = _v2_con_trabajo_id()
    V2.__name__ = NOMBRE_CONTRATO  # mismo nombre lógico que V1

    p1 = cliente.create_producer(topico, schema=AvroSchema(V1))
    p1.send(_mensaje_v1(V1))
    p1.close()
    print('  v1 (sin trabajo_id) registrado y publicado')

    try:
        p2 = cliente.create_producer(topico, schema=AvroSchema(V2))
        p2.send(_mensaje_v2(V2))
        p2.close()
    except Exception as e:
        print(f'  FALLA · el registro rechazó el campo nuevo: {type(e).__name__}: {e}')
        return False
    print('  v2 (con trabajo_id) ACEPTADO por el registro')

    # El consumidor viejo (esquema V1) sigue leyendo el mensaje nuevo.
    try:
        c = cliente.subscribe(
            topico, 'esc-e-lector-v1', schema=AvroSchema(V1),
            initial_position=pulsar.InitialPosition.Earliest,
        )
        m1 = c.receive(timeout_millis=8000)
        c.acknowledge(m1)
        m2 = c.receive(timeout_millis=8000)  # el mensaje v2
        c.acknowledge(m2)
        c.close()
    except Exception as e:
        print(f'  FALLA · el lector viejo no pudo leer el dato nuevo: {type(e).__name__}: {e}')
        return False
    print('  el consumidor con la versión ANTERIOR (sin trabajo_id) leyó el mensaje nuevo sin error')

    print('PASA · CA-E1')
    return True


def ca_e2(cliente, topico):
    print(f'\n=== CA-E2 · trabajo_id String -> Long (incompatible) — {topico}')
    V2 = _v2_con_trabajo_id()
    V2.__name__ = NOMBRE_CONTRATO

    p2 = cliente.create_producer(topico, schema=AvroSchema(V2))
    p2.send(_mensaje_v2(V2))
    p2.close()
    print('  v2 (trabajo_id: String) registrado')

    Incompatible = _v2_incompatible()
    try:
        cliente.create_producer(topico, schema=AvroSchema(Incompatible))
        print('  FALLA · el broker ACEPTÓ un cambio de tipo — no debería')
        return False
    except Exception as e:
        print(f'  el broker RECHAZÓ el cambio de tipo: {type(e).__name__}')

    print('PASA · CA-E2')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--broker', default='pulsar://localhost:6650')
    parser.add_argument('--listener', default='external')
    args = parser.parse_args()

    base = f'persistent://public/default/esquemas-esc-e-{int(time.time())}'
    cliente = pulsar.Client(args.broker, listener_name=args.listener or None, operation_timeout_seconds=15)

    try:
        ok_e1 = ca_e1(cliente, f'{base}-ca-e1')
        ok_e2 = ca_e2(cliente, f'{base}-ca-e2')
    finally:
        cliente.close()

    print('\n=== Resumen')
    print(f'CA-E1 · {"PASA" if ok_e1 else "FALLA"}')
    print(f'CA-E2 · {"PASA" if ok_e2 else "FALLA"}')

    if not (ok_e1 and ok_e2):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
