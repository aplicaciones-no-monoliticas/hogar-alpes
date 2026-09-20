"""US-02 · Verificación estática del aislamiento entre servicios.

"Los servicios de dominio no se alcanzan entre sí" significa que NO se llaman
por HTTP: se comunican solo por eventos de Pulsar. No significa aislamiento de
red (comparten `red-broker` y se resuelven por nombre). Por eso la regla se
comprueba sobre el código y la configuración, no probando que un nombre no
resuelva. Solo el BFF hace HTTP hacia adentro.

Solo lectura, solo biblioteca estándar. Cada criterio termina en PASA, FALLA o
PENDIENTE (lo que no se pudo comprobar, p. ej. sin Docker: nunca cuenta como
PASA). Código de salida 1 si algún criterio FALLA.

    python herramientas/verificar_aislamiento.py
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SERVICIOS = RAIZ / 'servicios'

DIRECTORIOS_DE_DOMINIO = ('_plantilla', 'gestion_trabajos', 'operaciones', 'acreditacion', 'emparejamiento')
CLIENTES_HTTP = ('urllib', 'requests', 'httpx', 'aiohttp', 'http.client', 'http://', 'https://')
DEPENDENCIAS_PROHIBIDAS_EN_BFF = ('pulsar-client', 'sqlalchemy', 'psycopg2')

fallos = 0
pendientes = 0


def informar(estado: str, criterio: str, detalle: str) -> None:
    global fallos, pendientes
    if estado == 'FALLA':
        fallos += 1
    elif estado == 'PENDIENTE':
        pendientes += 1
    print(f'  {estado:<9}  {criterio} · {detalle}')


def veredicto(criterio: str, problemas: list, detalle_ok: str) -> None:
    if problemas:
        informar('FALLA', criterio, f'{len(problemas)} problema(s)')
        for problema in problemas:
            print(f'             - {problema}')
    else:
        informar('PASA', criterio, detalle_ok)


def _relativo(ruta: Path) -> str:
    return ruta.relative_to(RAIZ).as_posix()


def _archivos_py(subdirectorio: str = 'src'):
    for directorio in DIRECTORIOS_DE_DOMINIO:
        yield from sorted((SERVICIOS / directorio / subdirectorio).rglob('*.py'))


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _compose_config():
    """Devuelve `(configuración, motivo_de_pendiente)`; una de las dos es `None`."""
    try:
        proceso = subprocess.run(
            ['docker', 'compose', 'config', '--format', 'json'],
            cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f'docker no está disponible ({type(error).__name__})'
    if proceso.returncode != 0:
        return None, f'`docker compose config` falló: {proceso.stderr.strip()[:200]}'
    return json.loads(proceso.stdout), None


def _familia(nombre: str, servicio: dict) -> str | None:
    """Nombre lógico de un servicio de dominio (`gestion-trabajos`), o `None` si no lo es."""
    contexto = ((servicio.get('build') or {}).get('context') or '').replace('\\', '/')
    partes = contexto.rstrip('/').split('/')
    if len(partes) < 2 or partes[-2] != 'servicios' or partes[-1] == 'bff':
        return None
    return partes[-1].replace('_', '-')


# --------------------------------------------------------------------- criterios

def ca_2_13_codigo() -> None:
    problemas = []
    for archivo in _archivos_py():
        texto = archivo.read_text(encoding='utf-8')
        for termino in CLIENTES_HTTP:
            if termino in texto:
                problemas.append(f'{_relativo(archivo)} contiene «{termino}»')
    veredicto('CA-2.13 (código)', problemas, 'ningún servicio de dominio tiene cliente HTTP ni literales http(s)://')


def ca_2_13_configuracion(compose) -> None:
    if compose is None:
        return
    servicios = compose['services']
    familias = {n: _familia(n, s) for n, s in servicios.items()}
    nombres = {f for f in familias.values() if f}
    problemas = []
    for nombre, servicio in servicios.items():
        familia = familias[nombre]
        if familia is None:
            continue
        otros = nombres - {familia}
        patron = re.compile(r'(?<![\w-])(' + '|'.join(re.escape(o) for o in sorted(otros)) + r')(?![\w-])')
        for variable, valor in (servicio.get('environment') or {}).items():
            valor = '' if valor is None else str(valor)
            if variable.startswith('URL_'):
                problemas.append(f'{nombre}: la variable {variable} solo la tiene el BFF')
            if patron.search(valor):
                problemas.append(f'{nombre}: {variable}={valor} apunta a otro servicio de dominio')
            if 'bff' in (variable + valor).lower():
                problemas.append(f'{nombre}: {variable}={valor} menciona al BFF')
    veredicto('CA-2.13 (configuración)', problemas, 'ninguna variable de un servicio de dominio apunta a otro servicio ni al BFF; solo el BFF tiene URL_*')


def ca_2_12_redes(compose) -> None:
    if compose is None:
        return
    servicios = compose['services']
    bff = servicios.get('bff')
    if bff is None:
        informar('FALLA', 'CA-2.12', 'no existe el servicio bff en docker-compose.yml')
        return
    problemas = []
    pendiente = []
    ajenas = [red for red in (bff.get('networks') or {}) if not red.startswith('red-bff-')]
    if ajenas:
        problemas.append(f'el BFF pertenece a redes que no son red-bff-*: {sorted(ajenas)}')
    redes_bff = sorted(r for r in compose.get('networks', {}) if r.startswith('red-bff-'))
    for red in redes_bff:
        miembros = sorted(n for n, s in servicios.items() if red in (s.get('networks') or {}))
        de_dominio = [n for n in miembros if _familia(n, servicios[n])]
        otros = [n for n in miembros if n != 'bff' and n not in de_dominio]
        if 'bff' not in miembros or otros:
            problemas.append(f'{red}: miembros inesperados {miembros}')
        elif len(de_dominio) == 0:
            pendiente.append(f'{red}: solo el BFF (el servicio de atrás todavía no existe)')
        elif len(de_dominio) != 1:
            problemas.append(f'{red}: debe tener el BFF y un servicio de dominio, tiene {miembros}')
    if problemas:
        veredicto('CA-2.12', problemas, '')
        return
    informar('PASA', 'CA-2.12', f'cada red red-bff-* tiene al BFF y a un solo servicio ({len(redes_bff) - len(pendiente)} de {len(redes_bff)}); el BFF no está en otras redes')
    for motivo in pendiente:
        informar('PENDIENTE', 'CA-2.12', motivo)


def ca_2_3(compose, motivo_sin_compose) -> None:
    requirements = (SERVICIOS / 'bff' / 'requirements.txt').read_text(encoding='utf-8').lower()
    problemas = [f'requirements.txt incluye {d}' for d in DEPENDENCIAS_PROHIBIDAS_EN_BFF if d in requirements]
    veredicto('CA-2.3 (requirements)', problemas, 'el BFF no depende de pulsar-client, SQLAlchemy ni psycopg2')
    if compose is None:
        informar('PENDIENTE', 'CA-2.3 (compose)', motivo_sin_compose)
        return
    bff = compose['services'].get('bff') or {}
    entorno = bff.get('environment') or {}
    problemas = []
    if bff.get('volumes'):
        problemas.append('declara volumes')
    for prohibida in ('DATABASE_URI', 'BROKER_HOST'):
        if prohibida in entorno:
            problemas.append(f'declara {prohibida}')
    if bff.get('depends_on'):
        problemas.append('declara depends_on (no podría arrancar con un servicio caído)')
    veredicto('CA-2.3 (compose)', problemas, 'el BFF no declara volúmenes, DATABASE_URI, BROKER_HOST ni depends_on')


def sin_llamadas_al_bff() -> None:
    problemas = [
        f'{_relativo(a)} menciona «bff»' for a in _archivos_py() if 'bff' in a.read_text(encoding='utf-8').lower()
    ]
    veredicto('Sin llamadas al BFF', problemas, 'ningún .py de los servicios de dominio menciona al BFF')


def ca_2_21() -> None:
    problemas = []
    for directorio in DIRECTORIOS_DE_DOMINIO:
        for archivo in sorted((SERVICIOS / directorio / 'src').rglob('*.py')):
            en_dominio = 'dominio' in archivo.relative_to(SERVICIOS / directorio).parts[:-1]
            if not (en_dominio or archivo.name == 'dto.py'):
                continue
            if re.search(r'correlation|correlacion', archivo.read_text(encoding='utf-8'), re.IGNORECASE):
                problemas.append(f'{_relativo(archivo)} menciona la correlación')
    veredicto('CA-2.21', problemas, 'el identificador de correlación no aparece en dominio/ ni en ningún dto.py')


def copias_identicas() -> None:
    copias = sorted(SERVICIOS.glob('*/src/*/**/correlacion.py'))
    problemas = []
    hashes = {_relativo(c): _sha256(c) for c in copias}
    if len(set(hashes.values())) > 1:
        problemas = [f'{ruta}: {h[:12]}' for ruta, h in hashes.items()]
        problemas.insert(0, 'las copias de correlacion.py difieren')
    if len(copias) < 6:
        problemas.append(f'se esperaban al menos 6 copias de correlacion.py y hay {len(copias)}')
    veredicto('Copias idénticas', problemas, f'las {len(copias)} copias de correlacion.py tienen el mismo SHA-256')


def sobre_sin_divergencia() -> None:
    referencia = SERVICIOS.parent / 'contratos' / 'v1' / 'mensajes.py'
    esperado = _sha256(referencia)
    problemas = []
    for directorio in ('_plantilla', 'acreditacion', 'emparejamiento'):
        for copia in (SERVICIOS / directorio / 'src').glob('*/seedwork/infraestructura/schema/v1/mensajes.py'):
            if _sha256(copia) != esperado:
                problemas.append(f'{_relativo(copia)} difiere de contratos/v1/mensajes.py')
    veredicto('sobre() sin divergencia', problemas, 'schema/v1/mensajes.py sigue idéntico a contratos/v1/mensajes.py')


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    print('# US-02 · Aislamiento entre servicios (verificación estática)')
    print()
    compose, motivo = _compose_config()
    ca_2_13_codigo()
    if compose is None:
        informar('PENDIENTE', 'CA-2.13 (configuración)', motivo)
        informar('PENDIENTE', 'CA-2.12', motivo)
    else:
        ca_2_13_configuracion(compose)
        ca_2_12_redes(compose)
    ca_2_3(compose, motivo)
    sin_llamadas_al_bff()
    ca_2_21()
    copias_identicas()
    sobre_sin_divergencia()
    print()
    if fallos:
        print(f'FALLA · {fallos} criterio(s) no se cumplen, {pendientes} pendiente(s)')
        return 1
    if pendientes:
        print(f'PASA con PENDIENTES · sin fallos, {pendientes} criterio(s) sin comprobar')
        return 0
    print('PASA · todos los criterios')
    return 0


if __name__ == '__main__':
    sys.exit(main())
