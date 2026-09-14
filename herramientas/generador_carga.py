"""HER-1 · Generador de carga — Entrega 4, Hogar de los Alpes.

Publica `CrearTrabajo` a una tasa y durante un tiempo dados. Simula el
Gateway o BFF de la Entrega 5 (§9 del plan técnico) — es el instrumento de los
escenarios 6 y 8.

Tres modos, elegidos por lo que se le pase:

  - `--via-http <url-base>` — el camino real hoy: `POST /trabajos` contra
    Gestión de Trabajos (GT-1, GT-2 ya están hechos). Mide la disponibilidad
    de GT (CA-6.1, CA-6.2) tal como lo vería un cliente externo.
  - `--topico cmd-trabajo-...` (por defecto, según el plan técnico §9) —
    publica `ComandoCrearTrabajo` directo al tópico de comandos. **Sin efecto
    todavía**: GT-4 (consumidor `cmd-trabajo-.*`) no está hecho, así que hoy
    nadie lee ese tópico. Queda listo para cuando GT-4 aterrice.
  - `--topico evt-trabajo-...` — publica `EventoTrabajo` (`TrabajoCreado`, y
    con `--con-cambios-estado` un `EstadoTrabajoCambiado` después) DIRECTO al
    stream de integración, sin pasar por GT. Es el mismo atajo que usó EMP-3
    (`docs/03-tareas.md` §5, nota de verificación): hasta que GT-3 unifique
    los tópicos (G-2), es la única manera de ejercitar el consumidor de
    Operaciones con el contrato real. `escenarios/escenario-6.sh` combina
    `--via-http` (para CA-6.1/6.2, el lado de GT) con este modo (para
    CA-6.3…6.6, el lado de Operaciones) — ver la nota al principio de ese
    script.

Reutiliza un solo cliente y un solo productor para todo el proceso (RNF-4).

Uso:
    # Carga sostenida: 500 trabajos a 20/s, vía HTTP contra GT
    python herramientas/generador_carga.py --via-http http://localhost:8000 \\
        --total 500 --tasa 20

    # Backlog sintético para el escenario 6 (bypass de GT, ver arriba)
    python herramientas/generador_carga.py \\
        --topico persistent://hogar-alpes/trabajos/evt-trabajo-andina \\
        --total 500 --con-cambios-estado

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

from contratos.v1.cmd_trabajo import TIPO_CREAR, ComandoCrearTrabajo  # noqa: E402
from contratos.v1.evt_trabajo import (  # noqa: E402
    TIPO_CREADO,
    TIPO_ESTADO_CAMBIADO,
    EventoTrabajo,
)
from contratos.v1.mensajes import sobre  # noqa: E402

PAISES_CIUDADES = {
    'CO': ['Bogota', 'Medellin', 'Cali'],
    'MX': ['CDMX', 'Monterrey', 'Guadalajara'],
    'BR': ['Sao Paulo', 'Rio de Janeiro'],
    'AR': ['Buenos Aires', 'Cordoba'],
}
CATEGORIAS = ['PLOMERIA', 'GAS', 'ELECTRICIDAD', 'CARPINTERIA', 'SINIESTRO_GRANIZO']
URGENCIAS = ['BAJA', 'NORMAL', 'ALTA', 'CRITICA']
CANALES = ['MARKETPLACE', 'APP', 'CALL_CENTER']
# Secuencia de estados que puede seguir un cambio, para --con-cambios-estado.
SIGUIENTE_ESTADO = {'CREADO': 'EMPAREJANDO', 'EMPAREJANDO': 'ASIGNADO'}


def _datos_trabajo(pais):
    return {
        'canal': random.choice(CANALES),
        'partner_id': f'partner-{random.randint(1, 20)}',
        'referencia_externa': str(uuid.uuid4())[:8],
        'categoria': random.choice(CATEGORIAS),
        'urgencia': random.choice(URGENCIAS),
        'pais': pais,
        'ciudad': random.choice(PAISES_CIUDADES[pais]),
        'direccion': 'Dirección de prueba 123',
        'descripcion': 'Generado por herramientas/generador_carga.py',
    }


def _publicar_via_comando(productor, trabajo_id, pais):
    datos = _datos_trabajo(pais)
    mensaje = ComandoCrearTrabajo(
        **sobre(TIPO_CREAR, 'generador-carga', correlation_id=trabajo_id),
        trabajo_id=trabajo_id, **datos,
    )
    productor.send_async(mensaje, partition_key=trabajo_id, callback=lambda *a: None)


def _publicar_via_evento(productor, trabajo_id, pais, con_cambios_estado):
    datos = _datos_trabajo(pais)
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


def _publicar_via_http(base_url, pais, timeout):
    datos = _datos_trabajo(pais)
    peticion = urllib.request.Request(
        f'{base_url.rstrip("/")}/trabajos',
        data=json.dumps(datos).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as resp:
            resp.read()
            return resp.status < 300
    except urllib.error.HTTPError as e:
        return e.code < 300
    except Exception:
        return False


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
                         help='(solo evt-trabajo-*) también publica un EstadoTrabajoCambiado por trabajo')
    parser.add_argument('--broker', default=os.getenv('BROKER_URL', 'pulsar://localhost:6650'))
    parser.add_argument('--listener', default=os.getenv('BROKER_LISTENER', 'external'))
    parser.add_argument('--paises', default=','.join(PAISES_CIUDADES),
                         help='lista separada por comas, p. ej. CO,MX')
    parser.add_argument('--progreso-cada', type=int, default=100)
    parser.add_argument('--semilla', type=int, default=None, help='para corridas reproducibles')
    parser.add_argument('--timeout-http', type=float, default=5.0)
    args = parser.parse_args()

    if args.semilla is not None:
        random.seed(args.semilla)
    paises = [p.strip() for p in args.paises.split(',') if p.strip() in PAISES_CIUDADES]
    if not paises:
        raise SystemExit(f'--paises no tiene ningún país conocido: {args.paises!r}')

    intervalo = (1.0 / args.tasa) if args.tasa > 0 else 0
    limite_tiempo = (time.time() + args.duracion) if args.duracion > 0 else None

    errores = 0
    inicio = time.time()

    if args.via_http:
        for i in range(args.total):
            if limite_tiempo and time.time() >= limite_tiempo:
                break
            ok = _publicar_via_http(args.via_http, random.choice(paises), args.timeout_http)
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
                _publicar_via_evento(productor, trabajo_id, pais, args.con_cambios_estado)
            else:
                _publicar_via_comando(productor, trabajo_id, pais)
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
