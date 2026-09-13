"""HER-2 · Medición de latencia — Entrega 4, Hogar de los Alpes.

Dispara peticiones HTTP concurrentes contra un endpoint y reporta p50/p95/p99 y
tasa de error. Solo biblioteca estándar: es el instrumento de dos criterios de
aceptación, no un servicio más que desplegar.

  - CA-6.2 — p95 de `POST /trabajos` durante la caída del escenario 6 (< 500 ms).
  - CA-8.2 — p95 de `GET /candidatos` con >= 100.000 proveedores (< 1 s).

Uso:
    python herramientas/medir_latencia.py http://localhost:8000/health

    python herramientas/medir_latencia.py \
        "http://localhost:8003/candidatos?categoria=PLOMERIA&pais=CO&ciudad=Bogota" \
        --peticiones 500 --concurrencia 20 --umbral-p95-ms 1000

    python herramientas/medir_latencia.py http://localhost:8000/trabajos --metodo POST \
        --cuerpo '{"categoria":"PLOMERIA","pais":"CO","ciudad":"Bogota","direccion":"Cra 7","urgencia":"NORMAL"}' \
        --umbral-p95-ms 500
"""
import argparse
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def _peticion(url: str, metodo: str, cuerpo: str | None, timeout: float):
    datos = cuerpo.encode('utf-8') if cuerpo else None
    cabeceras = {'Content-Type': 'application/json'} if cuerpo else {}
    peticion = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as resp:
            resp.read()
            return time.perf_counter() - inicio, resp.status, None
    except urllib.error.HTTPError as e:
        # Un 4xx/5xx sigue siendo una respuesta medible; solo cuenta como error
        # de disponibilidad si es 5xx (ver más abajo).
        return time.perf_counter() - inicio, e.code, None
    except Exception as e:
        return time.perf_counter() - inicio, None, type(e).__name__


def percentil(valores: list[float], p: float) -> float:
    """Interpolación lineal entre los dos valores más cercanos — sin depender
    de NumPy ni de `statistics.quantiles` (disponible solo desde 3.8, pero así
    el resultado no cambia entre versiones de Python del equipo)."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    posicion = (len(ordenados) - 1) * (p / 100)
    piso, techo = int(posicion), min(int(posicion) + 1, len(ordenados) - 1)
    if piso == techo:
        return ordenados[piso]
    return ordenados[piso] + (ordenados[techo] - ordenados[piso]) * (posicion - piso)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('url')
    parser.add_argument('--metodo', default='GET')
    parser.add_argument('--cuerpo', default=None, help='JSON crudo para POST/PUT')
    parser.add_argument('--peticiones', type=int, default=200)
    parser.add_argument('--concurrencia', type=int, default=10)
    parser.add_argument('--timeout', type=float, default=10.0)
    parser.add_argument(
        '--umbral-p95-ms', type=float, default=None,
        help='Si se da, el script termina en FALLA si el p95 lo supera',
    )
    args = parser.parse_args()

    latencias_ms: list[float] = []
    errores: list[str] = []
    codigos: dict = {}

    inicio_total = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrencia) as pool:
        futuros = [
            pool.submit(_peticion, args.url, args.metodo, args.cuerpo, args.timeout)
            for _ in range(args.peticiones)
        ]
        for futuro in as_completed(futuros):
            duracion, status, error = futuro.result()
            latencias_ms.append(duracion * 1000)
            codigos[status] = codigos.get(status, 0) + 1
            if error or status is None or status >= 500:
                errores.append(error or f'HTTP {status}')
    duracion_total = time.perf_counter() - inicio_total

    tasa_error = len(errores) / args.peticiones if args.peticiones else 0.0
    p50 = percentil(latencias_ms, 50)
    p95 = percentil(latencias_ms, 95)
    p99 = percentil(latencias_ms, 99)

    print(f'=== {args.metodo} {args.url}')
    print(f'peticiones      : {args.peticiones} (concurrencia {args.concurrencia})')
    print(f'duración total  : {duracion_total:.2f}s · {args.peticiones / duracion_total:.1f} req/s')
    print(f'códigos         : {codigos}')
    print(f'tasa de error   : {tasa_error * 100:.2f}% ({len(errores)}/{args.peticiones}, 5xx o excepción)')
    print(f'p50 / p95 / p99 : {p50:.1f} ms / {p95:.1f} ms / {p99:.1f} ms')

    fallos = []
    if errores:
        fallos.append(f'{len(errores)} peticiones fallaron')
    if args.umbral_p95_ms is not None and p95 > args.umbral_p95_ms:
        fallos.append(f'p95 {p95:.1f} ms > umbral {args.umbral_p95_ms} ms')

    print()
    if fallos:
        print('FALLA · ' + ' | '.join(fallos))
        raise SystemExit(1)
    print('PASA')


if __name__ == '__main__':
    main()
