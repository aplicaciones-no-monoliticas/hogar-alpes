"""HER-3 · Carga de acreditaciones — Entrega 4, Hogar de los Alpes.

Publica `<total>` proveedores por `cmd-acreditacion`: por cada uno,
`SolicitarAcreditacion` seguido de `AprobarAcreditacion`. Es el mismo camino
por el que entraría un proveedor real (§4.4 de la especificación:
*«la proyección se llena por el mismo camino que en producción, no con un
INSERT directo»*) — instrumento de CA-8.1.

Los dos comandos de un mismo proveedor comparten `partition_key=proveedor_id`,
así que caen en la misma partición y se procesan en orden: la aprobación no
puede adelantar a su solicitud (§3.2 del plan técnico).

Reutiliza un solo cliente y un solo productor para todo el proceso (RNF-4):
abrir una conexión por mensaje no soportaría 100.000 × 2 comandos.

Uso:
    # Prueba pequeña antes de la corrida grande (R-5 de la especificación):
    python herramientas/cargar_acreditaciones.py --total 1000

    # Corrida real, antes de la demo (tarda minutos):
    python herramientas/cargar_acreditaciones.py --total 100000

Desde el host hace falta `--listener external` (por defecto), porque los
brokers anuncian su dirección interna (`broker-N:6650`) — ver INF-2 en
`docs/decisiones.md`.
"""
import argparse
import os
import random
import sys
import time
import uuid

import pulsar
from pulsar.schema import AvroSchema

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from contratos.v1.cmd_acreditacion import APROBAR, SOLICITAR, ComandoAcreditacion  # noqa: E402
from contratos.v1.mensajes import sobre  # noqa: E402

PAISES_CIUDADES = {
    'CO': ['Bogota', 'Medellin', 'Cali'],
    'MX': ['CDMX', 'Monterrey', 'Guadalajara'],
    'BR': ['Sao Paulo', 'Rio de Janeiro'],
    'AR': ['Buenos Aires', 'Cordoba'],
}
CATEGORIAS = ['PLOMERIA', 'GAS', 'ELECTRICIDAD', 'CARPINTERIA', 'SINIESTRO_GRANIZO']
NIVELES = ['BASICO', 'PLATA', 'ORO']


def _comando(tipo, acreditacion_id, proveedor_id, pais, ciudad, categorias, nivel,
             vigencia_meses, motivo=''):
    tipo_evento = f'hogaralpes.acreditacion.{tipo.lower().replace("acreditacion", "")}.v1'
    return ComandoAcreditacion(
        **sobre(tipo_evento, 'cargar-acreditaciones', correlation_id=proveedor_id),
        tipo_comando=tipo, acreditacion_id=acreditacion_id, proveedor_id=proveedor_id,
        pais=pais, ciudad=ciudad, categorias=categorias, nivel=nivel,
        vigencia_meses=vigencia_meses, motivo=motivo,
    )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--total', type=int, default=100_000, help='proveedores a cargar')
    parser.add_argument('--broker', default=os.getenv('BROKER_URL', 'pulsar://localhost:6650'))
    parser.add_argument('--listener', default=os.getenv('BROKER_LISTENER', 'external'))
    parser.add_argument(
        '--topico', default='persistent://hogar-alpes/acreditacion/cmd-acreditacion',
    )
    parser.add_argument('--vigencia-meses', type=int, default=12)
    parser.add_argument('--paises', default=','.join(PAISES_CIUDADES),
                         help='lista separada por comas, p. ej. CO,MX')
    parser.add_argument('--progreso-cada', type=int, default=5000)
    parser.add_argument('--semilla', type=int, default=None, help='para corridas reproducibles')
    args = parser.parse_args()

    if args.semilla is not None:
        random.seed(args.semilla)
    paises = [p.strip() for p in args.paises.split(',') if p.strip() in PAISES_CIUDADES]
    if not paises:
        raise SystemExit(f'--paises no tiene ningún país conocido: {args.paises!r}')

    cliente = pulsar.Client(
        args.broker, listener_name=args.listener or None, operation_timeout_seconds=30,
    )
    productor = cliente.create_producer(args.topico, schema=AvroSchema(ComandoAcreditacion))

    fallos = []

    def _en_error(resultado, mensaje_id):
        if resultado != pulsar.Result.Ok:
            fallos.append(resultado)

    inicio = time.time()
    try:
        for i in range(args.total):
            proveedor_id = str(uuid.uuid4())
            acreditacion_id = str(uuid.uuid4())
            pais = random.choice(paises)
            ciudad = random.choice(PAISES_CIUDADES[pais])
            categorias = random.sample(CATEGORIAS, k=random.randint(1, 2))
            nivel = random.choice(NIVELES)

            productor.send_async(
                _comando(SOLICITAR, acreditacion_id, proveedor_id, pais, ciudad,
                         categorias, nivel, args.vigencia_meses),
                partition_key=proveedor_id, callback=_en_error,
            )
            productor.send_async(
                _comando(APROBAR, acreditacion_id, proveedor_id, pais, ciudad,
                         categorias, nivel, args.vigencia_meses, motivo='carga masiva'),
                partition_key=proveedor_id, callback=_en_error,
            )

            if (i + 1) % args.progreso_cada == 0:
                transcurrido = time.time() - inicio
                tasa = ((i + 1) * 2) / transcurrido if transcurrido else 0
                print(f'  {i + 1}/{args.total} proveedores · {transcurrido:.1f}s · {tasa:.0f} msg/s')

        productor.flush()
    finally:
        cliente.close()

    duracion = time.time() - inicio
    total_mensajes = args.total * 2
    print(f'\n{args.total} proveedores · {total_mensajes} comandos publicados en {duracion:.1f}s '
          f'({total_mensajes / duracion:.0f} msg/s)')

    if fallos:
        print(f'FALLA · {len(fallos)} mensajes no confirmados por el broker: {fallos[:5]}')
        raise SystemExit(1)
    print('PASA · todos los comandos fueron confirmados por el broker')


if __name__ == '__main__':
    main()
