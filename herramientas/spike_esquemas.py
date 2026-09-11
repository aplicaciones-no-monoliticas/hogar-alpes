"""INF-0 · Spike de esquemas — Entrega 4, Hogar de los Alpes.

Responde las preguntas de las que depende la regla de evolución (plan §2.5):

  P1. ¿El consumidor decodifica con el esquema del ESCRITOR o con el suyo?
  P2. ¿Orden de campos: declaración o alfabético?
  P3. ¿El registro acepta una evolución compatible y rechaza una incompatible?
  P4. (nuevo, tras el primer intento) ¿Hace falta declarar `default` explícito para
      que el broker considere compatible agregar un campo?

Cada experimento usa su propio tópico y atrapa sus errores, para que una falla no
tumbe el resto de la corrida.
"""
import time
import traceback

import pulsar
from pulsar.schema import AvroSchema, Long, Record, String

SERVICIO = 'pulsar://localhost:6650'
# Desde el host hay que pedir el listener `external`: los brokers anuncian su
# dirección interna (broker-N:6650), que no resuelve fuera de la red de Docker.
# Ver docs/decisiones.md · INF-2.
LISTENER = 'external'
BASE = f'persistent://public/default/spike-{int(time.time())}'

R = {}


def titulo(t):
    print(f'\n{"=" * 78}\n{t}\n{"=" * 78}')


def campos(cls):
    return [(f['name'], f.get('type'), 'default' in f) for f in cls.schema()['fields']]


# ---------------------------------------------------------------- EXP A
def exp_a_defaults():
    titulo('A · ¿El esquema generado incluye "default"?')

    class SinDefault(Record):
        a = String()

    class ConDefaultSinBandera(Record):
        a = String(default='')

    class ConDefaultNulo(Record):
        a = String(default=None, required_default=True)

    for nombre, cls in [('String()', SinDefault),
                        ("String(default='')", ConDefaultSinBandera),
                        ('String(default=None, required_default=True)', ConDefaultNulo)]:
        print(f'{nombre:45} -> {cls.schema()["fields"]}')

    lleva_default = 'default' in ConDefaultNulo.schema()['fields'][0]
    R['A'] = ('required_default=True SÍ emite "default": null'
              if lleva_default else 'ni con required_default se emite el default')
    print(f'-> {R["A"]}')


# ---------------------------------------------------------------- EXP B y C
def evolucion(cliente, topico, V1, V2, etiqueta):
    """Registra V1 y luego intenta registrar V2 (un campo opcional más)."""
    try:
        p1 = cliente.create_producer(topico, schema=AvroSchema(V1))
        p1.send(V1(a='uno', b='dos'))
        p1.close()
        print(f'[{etiqueta}] v1 registrado y publicado')
    except Exception as e:
        print(f'[{etiqueta}] v1 FALLÓ: {type(e).__name__}: {e}')
        return f'v1 falló ({type(e).__name__})'

    try:
        p2 = cliente.create_producer(topico, schema=AvroSchema(V2))
        p2.send(V2(a='uno', b='dos', c='tres'))
        p2.close()
        print(f'[{etiqueta}] v2 (campo nuevo al final) ACEPTADO')
        return 'ACEPTADO'
    except Exception as e:
        print(f'[{etiqueta}] v2 RECHAZADO: {type(e).__name__}: {e}')
        return f'RECHAZADO ({type(e).__name__})'


def clases_sin_default():
    class EventoSpike(Record):
        a = String()
        b = String()

    class EventoSpike2(Record):
        a = String()
        b = String()
        c = String()

    EventoSpike2.__name__ = 'EventoSpike'
    return EventoSpike, EventoSpike2


def clases_con_default():
    """La declaración que sí emite `"default": null` en el esquema Avro."""
    class EventoSpikeD(Record):
        a = String(default=None, required_default=True)
        b = String(default=None, required_default=True)

    class EventoSpikeD2(Record):
        a = String(default=None, required_default=True)
        b = String(default=None, required_default=True)
        c = String(default=None, required_default=True)

    EventoSpikeD2.__name__ = 'EventoSpikeD'
    return EventoSpikeD, EventoSpikeD2


# ---------------------------------------------------------------- EXP D
def exp_d_lectores(cliente, topico, V1, V2):
    """¿Lee un consumidor viejo un dato nuevo, y uno nuevo un dato viejo?"""
    titulo('D · P1 · Lectores en las dos direcciones')
    resultado = {}

    for etiqueta, lector_cls, sub in [('lector v2 (nuevo)', V2, 'sub-v2'),
                                      ('lector v1 (viejo)', V1, 'sub-v1')]:
        try:
            c = cliente.subscribe(topico, sub, schema=AvroSchema(lector_cls),
                                  initial_position=pulsar.InitialPosition.Earliest)
        except Exception as e:
            print(f'{etiqueta}: no pudo suscribirse -> {type(e).__name__}: {e}')
            resultado[etiqueta] = f'suscripción rechazada ({type(e).__name__})'
            continue

        leidos = []
        for _ in range(2):
            try:
                m = c.receive(timeout_millis=8000)
                v = m.value()
                leidos.append({k: getattr(v, k, None) for k in ('a', 'b', 'c') if hasattr(v, k)})
                c.acknowledge(m)
            except Exception as e:
                leidos.append(f'ERROR {type(e).__name__}')
                break
        print(f'{etiqueta}: {leidos}')
        resultado[etiqueta] = leidos
        c.close()

    return resultado


# ---------------------------------------------------------------- EXP E
def exp_e_incompatible(cliente, topico, V1):
    titulo('E · ¿El broker rechaza un cambio de tipo (String -> Long)?')

    class EventoIncompatible(Record):
        a = Long()
        b = String()

    EventoIncompatible.__name__ = V1.__name__
    try:
        cliente.create_producer(topico, schema=AvroSchema(EventoIncompatible))
        print('ACEPTADO — la política no está protegiendo')
        return 'ACEPTADO (no esperado)'
    except Exception as e:
        print(f'RECHAZADO: {type(e).__name__}')
        return f'RECHAZADO ({type(e).__name__})'


def main():
    exp_a_defaults()

    cliente = pulsar.Client(SERVICIO, listener_name=LISTENER, operation_timeout_seconds=15)
    try:
        titulo('B · Evolución SIN default explícito')
        V1, V2 = clases_sin_default()
        R['B'] = evolucion(cliente, f'{BASE}-sin-default', V1, V2, 'sin default')

        titulo('C · Evolución CON default explícito')
        D1, D2 = clases_con_default()
        topico_d = f'{BASE}-con-default'
        R['C'] = evolucion(cliente, topico_d, D1, D2, 'con default')

        if R['C'] == 'ACEPTADO':
            R['D'] = exp_d_lectores(cliente, topico_d, D1, D2)
        else:
            V1b, V2b = clases_sin_default()
            R['D'] = exp_d_lectores(cliente, f'{BASE}-sin-default', V1b, V2b)

        R['E'] = exp_e_incompatible(cliente, f'{BASE}-con-default', D1)
    finally:
        cliente.close()

    titulo('RESUMEN')
    for k in sorted(R):
        print(f'{k}: {R[k]}')
    print(f'\nTópicos: {BASE}-*')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
