"""La tabla de reenvío coincide con las rutas reales de los servicios (R5-10).

Lee el código fuente de cada servicio, así que si una ruta cambia allá y el
BFF no, esta prueba lo detecta. Las tres de `saga-log` no tienen fuente todavía.
"""
import re
from pathlib import Path

from bff import rutas

SERVICIOS = Path(__file__).resolve().parents[2]

DIRECTORIOS = ('gestion_trabajos', 'operaciones', 'acreditacion', 'emparejamiento')

BLUEPRINT = re.compile(r"Blueprint\(\s*'[^']*'\s*,\s*__name__(?:\s*,\s*url_prefix\s*=\s*'([^']*)')?")
RUTA = re.compile(r"@bp\.route\(\s*'([^']*)'(?:\s*,\s*methods\s*=\s*\[([^\]]*)\])?")


def _rutas_de(servicio: str) -> set:
    encontradas = set()
    for archivo in (SERVICIOS / servicio / 'src').glob('*/api/*.py'):
        if archivo.name == 'salud.py':
            continue
        fuente = archivo.read_text(encoding='utf-8')
        blueprint = BLUEPRINT.search(fuente)
        if blueprint is None:
            continue
        prefijo = blueprint.group(1) or ''
        for ruta, metodos in RUTA.findall(fuente):
            patron = re.sub(r'<[^>]+>', '<id>', prefijo + ruta)
            for metodo in re.findall(r"'([A-Z]+)'", metodos):
                encontradas.add((metodo, patron))
    return encontradas


def test_la_tabla_tiene_diecisiete_reglas():
    assert len(rutas.RUTAS) == 17


def test_las_rutas_de_los_servicios_existentes_son_catorce():
    reales = set().union(*(_rutas_de(s) for s in DIRECTORIOS))
    assert len(reales) == 14


def test_la_tabla_coincide_con_las_rutas_reales_de_los_servicios():
    reales = set().union(*(_rutas_de(s) for s in DIRECTORIOS))
    de_la_tabla = {(r.metodo, r.patron) for r in rutas.RUTAS if r.servicio != 'saga-log'}
    assert de_la_tabla == reales


def test_cada_servicio_recibe_solo_sus_rutas():
    por_servicio = {
        'gestion-trabajos': _rutas_de('gestion_trabajos'),
        'operaciones': _rutas_de('operaciones'),
        'acreditacion': _rutas_de('acreditacion'),
        'emparejamiento': _rutas_de('emparejamiento'),
    }
    for servicio, reales in por_servicio.items():
        de_la_tabla = {(r.metodo, r.patron) for r in rutas.RUTAS if r.servicio == servicio}
        assert de_la_tabla == reales, servicio
