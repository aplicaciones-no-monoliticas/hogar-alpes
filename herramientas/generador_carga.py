"""HER-1 · Generador de carga — Entrega 4, Hogar de los Alpes.

Publica `CrearTrabajo` a una tasa y durante un tiempo dados. Simula el
Gateway o BFF de la Entrega 5 (§9 del plan técnico) — es el instrumento de los
escenarios 6 y 8.

Tres modos, elegidos por lo que se le pase:

  - `--via-http <url-base>` — el camino real: `POST /trabajos` contra
    Gestión de Trabajos. Desde GT-3, GT publica el `TrabajoCreado` real en
    `evt-trabajo-{región}`, así que este modo ya alimenta a Operaciones y
    Emparejamiento de punta a punta, no solo mide la disponibilidad de GT
    (CA-6.1, CA-6.2). Con `--con-cambios-estado`, además hace
    `PUT /trabajos/{id}/estado` por cada trabajo creado (`EMPAREJANDO`): es
    lo que ejercita `EstadoTrabajoCambiado` para CA-6.5 sin tocar Pulsar.
  - `--topico cmd-trabajo-...` (según el plan técnico §9) — publica
    `ComandoCrearTrabajo` directo al tópico de comandos, que GT-4 consume por
    patrón (Shared). Alternativa a `--via-http` cuando se quiere ejercitar el
    camino asíncrono de creación en vez del síncrono.
  - `--topico evt-trabajo-...` — publica `EventoTrabajo` DIRECTO al stream de
    integración, sin pasar por GT. Es el atajo que usó `escenario-8.sh` para
    precargar un backlog de drenaje (no necesita que exista un `Trabajo` real
    en la base de GT, solo el evento) y el que usó `escenario-6.sh` mientras
    GT-3 no estaba — ya no hace falta para el escenario 6 (`docs/decisiones.md`,
    sección GT-3), pero sigue siendo el modo correcto para backlogs sintéticos.

Reutiliza un solo cliente y un solo productor para todo el proceso (RNF-4).

Uso:
    # Carga sostenida: 500 trabajos a 20/s, vía HTTP contra GT — con GT-3,
    # esto ya llega de punta a punta a Operaciones y Emparejamiento.
    python herramientas/generador_carga.py --via-http http://localhost:8000 \\
        --total 500 --tasa 20 --con-cambios-estado

    # Backlog sintético para el escenario 8 (lo usa escenarios/escenario-8.sh)
    python herramientas/generador_carga.py \\
        --topico persistent://hogar-alpes/trabajos/evt-trabajo-andina --total 2000
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Los contratos importan `pulsar.schema`: en modo --via-http no hace falta
# tener pulsar-client instalado en absoluto (es HTTP puro contra GT), así que
# estos imports se difieren a donde realmente se usan (_publicar_via_comando,
# _publicar_via_evento, y el bloque de Pulsar en main), no al nivel del
# módulo. Sin esto, `--via-http` fallaba con ModuleNotFoundError('pulsar')
# incluso sin necesitarlo para nada.

PAISES_CIUDADES = {
    'CO': ['Bogota', 'Medellin', 'Cali'],
    'MX': ['CDMX', 'Monterrey', 'Guadalajara'],
    'BR': ['Sao Paulo', 'Rio de Janeiro'],
    'AR': ['Buenos Aires', 'Cordoba'],
}
# Los únicos valores que el objeto valor Canal de GT acepta
# (dominio/objetos_valor.py) — 'APP'/'CALL_CENTER' no existen ahí, y GT no
# atrapa ese ValueError en la API: revienta con 500 en vez de 400.
CANALES = ['MARKETPLACE', 'B2B2C']
# Secuencia de estados que puede seguir un cambio, para --con-cambios-estado.
SIGUIENTE_ESTADO = {'CREADO': 'EMPAREJANDO', 'EMPAREJANDO': 'ASIGNADO'}

RUTA_REGLAS_POR_DEFECTO = os.path.join(
    os.path.dirname(__file__), '..', 'infra', 'sidecar', 'reglas_regionales.json',
)
# Si el sidecar no está disponible (p. ej. corriendo fuera de este repo),
# categorías/urgencias genéricas que el _default del sidecar real también
# acepta — mejor que inventar combinaciones que GT rechazaría siempre.
_REGLAS_RESPALDO = {'_default': {'categorias': ['PLOMERIA', 'ELECTRICIDAD'],
                                  'urgencias': ['NORMAL', 'ALTA']}}


def _cargar_reglas(ruta):
    """Mismo archivo que lee el sidecar de GT (infra/sidecar/reglas_regionales.json,
    ver infra/sidecar/README.md). Sin esto, --categorias/--urgencias generados al
    azar violan las reglas del país la mayoría de las veces (p. ej. CARPINTERIA no
    aplica en NINGÚN país, GAS solo en AR, BAJA no aplica en MX ni AR) y GT los
    rechaza con 400 — no es un fallo de GT, es el generador ignorando la regla que
    el propio escenario 2 existe para demostrar."""
    try:
        with open(ruta, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f'AVISO: no se pudo leer {ruta} ({e}); usando un respaldo genérico', file=sys.stderr)
        return _REGLAS_RESPALDO


def _datos_trabajo(pais, reglas):
    region = reglas.get(pais, reglas.get('_default', _REGLAS_RESPALDO['_default']))
    return {
        'canal': random.choice(CANALES),
        'partner_id': f'partner-{random.randint(1, 20)}',
        'referencia_externa': str(uuid.uuid4())[:8],
        'categoria': random.choice(region['categorias']),
        'urgencia': random.choice(region['urgencias']),
        'pais': pais,
        'ciudad': random.choice(PAISES_CIUDADES[pais]),
        'direccion': 'Dirección de prueba 123',
        'descripcion': 'Generado por herramientas/generador_carga.py',
    }


def _publicar_via_comando(productor, trabajo_id, pais, reglas):
    from contratos.v1.cmd_trabajo import TIPO_CREAR, ComandoCrearTrabajo
    from contratos.v1.mensajes import sobre

    datos = _datos_trabajo(pais, reglas)
    mensaje = ComandoCrearTrabajo(
        **sobre(TIPO_CREAR, 'generador-carga', correlation_id=trabajo_id),
        trabajo_id=trabajo_id, **datos,
    )
    productor.send_async(mensaje, partition_key=trabajo_id, callback=lambda *a: None)


def _publicar_via_evento(productor, trabajo_id, pais, con_cambios_estado, reglas):
    from contratos.v1.evt_trabajo import TIPO_CREADO, TIPO_ESTADO_CAMBIADO, EventoTrabajo
    from contratos.v1.mensajes import sobre

    datos = _datos_trabajo(pais, reglas)
    creado = EventoTrabajo(
        **sobre(TIPO_CREADO, 'generador-carga', correlation_id=trabajo_id),
        trabajo_id=trabajo_id, partner_id=datos['partner_id'], canal=datos['canal'],
        pais=pais, ciudad=datos['ciudad'], categoria=datos['categoria'],
        urgencia=datos['urgencia'], estado='CREADO', estado_anterior='',
    )
    productor.send_async(
        creado, partition_key=trabajo_id, properties={'partner_id': datos['partner_id']},
        callback=lambda *a: None,
    )
    if not con_cambios_estado:
        return
    estado_anterior = 'CREADO'
    estado_nuevo = SIGUIENTE_ESTADO.get(estado_anterior)
    if not estado_nuevo:
        return
    cambio = EventoTrabajo(
        **sobre(TIPO_ESTADO_CAMBIADO, 'generador-carga', correlation_id=trabajo_id),
        trabajo_id=trabajo_id, partner_id=datos['partner_id'], canal=datos['canal'],
        pais=pais, ciudad=datos['ciudad'], categoria=datos['categoria'],
        urgencia=datos['urgencia'], estado=estado_nuevo, estado_anterior=estado_anterior,
    )
    productor.send_async(
        cambio, partition_key=trabajo_id, properties={'partner_id': datos['partner_id']},
        callback=lambda *a: None,
    )


def _http(url, metodo, cuerpo, timeout):
    peticion = urllib.request.Request(
        url,
        data=json.dumps(cuerpo).encode('utf-8') if cuerpo is not None else None,
        headers={'Content-Type': 'application/json'} if cuerpo is not None else {},
        method=metodo,
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as resp:
            cuerpo_resp = resp.read()
            return resp.status < 300, cuerpo_resp
    except urllib.error.HTTPError as e:
        return e.code < 300, e.read()
    except Exception:
        return False, b''


def _publicar_via_http(base_url, pais, timeout, con_cambios_estado, reglas):
    datos = _datos_trabajo(pais, reglas)
    ok, cuerpo_resp = _http(f'{base_url.rstrip("/")}/trabajos', 'POST', datos, timeout)
    if not ok or not con_cambios_estado:
        return ok

    # EMPAREJANDO es una transición válida desde CREADO (dominio/objetos_valor.py):
    # ejercita EstadoTrabajoCambiado para CA-6.5 sin tocar Pulsar directamente.
    try:
        trabajo_id = json.loads(cuerpo_resp).get('id', '')
    except Exception:
        return False
    if not trabajo_id:
        return False
    ok_estado, _ = _http(
        f'{base_url.rstrip("/")}/trabajos/{trabajo_id}/estado', 'PUT',
        {'estado': 'EMPAREJANDO'}, timeout,
    )
    return ok_estado


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--total', type=int, default=500, help='trabajos a generar')
    parser.add_argument('--tasa', type=float, default=0,
                         help='mensajes por segundo; 0 = tan rápido como se pueda')
    parser.add_argument('--duracion', type=float, default=0,
                         help='segundos máximos de corrida; 0 = sin límite (solo --total)')
    parser.add_argument('--via-http', default='', metavar='URL_BASE',
                         help='POST /trabajos contra esta URL en lugar de publicar en Pulsar')
    parser.add_argument('--topico', default='persistent://hogar-alpes/trabajos/cmd-trabajo-andina',
                         help='tópico Pulsar; cmd-trabajo-* publica el comando, '
                              'evt-trabajo-* publica el evento de integración directo (bypass de GT)')
    parser.add_argument('--con-cambios-estado', action='store_true',
                         help='también genera un cambio de estado por trabajo '
                              '(PUT /estado en --via-http, EstadoTrabajoCambiado en evt-trabajo-*)')
    parser.add_argument('--broker', default=os.getenv('BROKER_URL', 'pulsar://localhost:6650'))
    parser.add_argument('--listener', default=os.getenv('BROKER_LISTENER', 'external'))
    parser.add_argument('--paises', default=','.join(PAISES_CIUDADES),
                         help='lista separada por comas, p. ej. CO,MX')
    parser.add_argument('--progreso-cada', type=int, default=100)
    parser.add_argument('--semilla', type=int, default=None, help='para corridas reproducibles')
    parser.add_argument('--timeout-http', type=float, default=5.0)
    parser.add_argument('--reglas', default=RUTA_REGLAS_POR_DEFECTO,
                         help='reglas_regionales.json a respetar al elegir categoría/urgencia '
                              '(el mismo que lee el sidecar de GT) — evita generar combinaciones '
                              'que el escenario 2 rechazaría con 400, ajenas a lo que se mide aquí')
    args = parser.parse_args()

    if args.semilla is not None:
        random.seed(args.semilla)
    paises = [p.strip() for p in args.paises.split(',') if p.strip() in PAISES_CIUDADES]
    if not paises:
        raise SystemExit(f'--paises no tiene ningún país conocido: {args.paises!r}')
    reglas = _cargar_reglas(args.reglas)

    intervalo = (1.0 / args.tasa) if args.tasa > 0 else 0
    limite_tiempo = (time.time() + args.duracion) if args.duracion > 0 else None

    errores = 0
    inicio = time.time()

    if args.via_http:
        for i in range(args.total):
            if limite_tiempo and time.time() >= limite_tiempo:
                break
            ok = _publicar_via_http(
                args.via_http, random.choice(paises), args.timeout_http, args.con_cambios_estado,
                reglas,
            )
            if not ok:
                errores += 1
            if (i + 1) % args.progreso_cada == 0:
                _progreso(i + 1, args.total, inicio)
            if intervalo:
                time.sleep(intervalo)
        total_enviados = i + 1 if args.total else 0
        _resumen(total_enviados, errores, inicio, f'POST {args.via_http}/trabajos')
        raise SystemExit(1 if errores else 0)

    import pulsar
    from pulsar.schema import AvroSchema

    from contratos.v1.cmd_trabajo import ComandoCrearTrabajo
    from contratos.v1.evt_trabajo import EventoTrabajo

    es_evento = 'evt-trabajo' in args.topico
    schema = EventoTrabajo if es_evento else ComandoCrearTrabajo

    cliente = pulsar.Client(
        args.broker, listener_name=args.listener or None, operation_timeout_seconds=30,
    )
    productor = cliente.create_producer(args.topico, schema=AvroSchema(schema))
    try:
        i = -1
        for i in range(args.total):
            if limite_tiempo and time.time() >= limite_tiempo:
                break
            trabajo_id = str(uuid.uuid4())
            pais = random.choice(paises)
            if es_evento:
                _publicar_via_evento(productor, trabajo_id, pais, args.con_cambios_estado, reglas)
            else:
                _publicar_via_comando(productor, trabajo_id, pais, reglas)
            if (i + 1) % args.progreso_cada == 0:
                _progreso(i + 1, args.total, inicio)
            if intervalo:
                time.sleep(intervalo)
        productor.flush()
    finally:
        cliente.close()

    _resumen(i + 1, 0, inicio, f'tópico {args.topico}')


def _progreso(hechos, total, inicio):
    transcurrido = time.time() - inicio
    tasa = hechos / transcurrido if transcurrido else 0
    print(f'  {hechos}/{total} · {transcurrido:.1f}s · {tasa:.1f} msg/s')


def _resumen(total, errores, inicio, destino):
    duracion = time.time() - inicio
    tasa = total / duracion if duracion else 0
    print(f'\n{total} trabajos publicados hacia {destino} en {duracion:.1f}s ({tasa:.1f} msg/s)')
    if errores:
        print(f'FALLA · {errores} publicaciones fallaron')
    else:
        print('PASA · todas las publicaciones se confirmaron')


if __name__ == '__main__':
    main()
