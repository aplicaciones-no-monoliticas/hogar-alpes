"""Endpoints compuestos: consultas que juntan lo que está repartido entre servicios.

Las llamadas de una fase van en paralelo, cada una con su propio tiempo límite,
y una parte que falla se marca en lugar de tumbar la respuesta entera.
"""
import contextvars
import json
import logging
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import NamedTuple

from flask import Blueprint, current_app, g, jsonify

from . import cliente, correlacion, errores, reenvio

logger = logging.getLogger(__name__)
compuestos_bp = Blueprint('compuestos', __name__)

SERVICIOS_DE_ATRAS = ('gestion-trabajos', 'operaciones', 'acreditacion', 'emparejamiento', 'saga-log')


def parte_disponible(datos) -> dict:
    return {'estado': 'DISPONIBLE', 'datos': datos}


def parte_todavia_no_disponible() -> dict:
    return {'estado': 'TODAVIA_NO_DISPONIBLE'}


def parte_no_disponible(servicio: str, motivo: str) -> dict:
    return {'estado': 'NO_DISPONIBLE', 'servicio': servicio, 'motivo': motivo}


class Consulta(NamedTuple):
    """`parte` es lo que se muestra; `cruda` solo viene en un `404` de una parte raíz."""

    parte: dict | None
    cruda: cliente.Respuesta | None = None


def consultar(configuracion, servicio: str, ruta: str, raiz: bool = False, consulta: bytes = b'') -> Consulta:
    """Clasifica una llamada `GET` a un servicio de atrás (data-model §6).

    Corre en un hilo: no usa `flask.g` ni `request`, todo llega por argumentos.
    """
    try:
        respuesta = cliente.llamar(
            configuracion.servicios[servicio], 'GET', ruta,
            consulta=consulta, timeout=configuracion.timeout_compuesto_s,
        )
    except cliente.FalloAtras as fallo:
        return Consulta(parte_no_disponible(fallo.servicio, fallo.motivo))

    if respuesta.codigo == 404:
        return Consulta(None, respuesta) if raiz else Consulta(parte_todavia_no_disponible())
    if respuesta.codigo == 200:
        try:
            return Consulta(parte_disponible(json.loads(respuesta.cuerpo)))
        except ValueError:
            pass
    logger.warning('Respuesta inesperada de %s en %s: %s', servicio, ruta, respuesta.codigo)
    return Consulta(parte_no_disponible(servicio, 'RESPUESTA_INESPERADA'))


def en_paralelo(tareas: dict) -> dict:
    """Ejecuta las tareas a la vez; cada una en una copia del contexto para que el identificador de correlación llegue al hilo."""
    with ThreadPoolExecutor(max_workers=max(1, len(tareas))) as pool:
        futuros = {nombre: pool.submit(contextvars.copy_context().run, tarea) for nombre, tarea in tareas.items()}
        return {nombre: futuro.result() for nombre, futuro in futuros.items()}


def consolidar(consultas: dict, encabezado: dict):
    """Un `404` raíz pasa tal cual; si todas las partes fallan, `503`; si no, `200`."""
    for consulta in consultas.values():
        if consulta.cruda is not None:
            return reenvio.a_respuesta_flask(consulta.cruda)
    partes = {nombre: consulta.parte for nombre, consulta in consultas.items()}
    if all(parte['estado'] == 'NO_DISPONIBLE' for parte in partes.values()):
        nombres = list(dict.fromkeys(parte['servicio'] for parte in partes.values()))
        return errores.servicios_no_disponibles(nombres)
    return jsonify({**encabezado, 'correlation_id': correlacion.actual(), 'partes': partes})


@compuestos_bp.route('/trabajos/<id>/completo', methods=['GET'])
def trabajo_completo(id):
    g.servicio_destino = 'compuesto'
    correlacion.agregar_campos(trabajo_id=id)
    configuracion = current_app.config['BFF']
    consultas = en_paralelo({
        'trabajo': partial(consultar, configuracion, 'gestion-trabajos', f'/trabajos/{id}', raiz=True),
        'seguimiento': partial(consultar, configuracion, 'operaciones', f'/seguimientos/{id}'),
        'emparejamiento': partial(consultar, configuracion, 'emparejamiento', f'/emparejamientos/{id}'),
        'saga': partial(consultar, configuracion, 'saga-log', f'/sagas/{id}'),
    })
    return consolidar(consultas, {'trabajo_id': id})


def _candidato(configuracion, acreditacion: dict) -> dict:
    """¿Aparece el proveedor hoy como candidato? Una consulta por categoría de su acreditación."""
    proveedor_id = acreditacion.get('proveedor_id')
    categorias = list(dict.fromkeys(acreditacion.get('categorias') or []))
    consultas = en_paralelo({
        categoria: partial(
            consultar, configuracion, 'emparejamiento', '/candidatos',
            consulta=urllib.parse.urlencode({
                'categoria': categoria,
                'pais': acreditacion.get('pais', ''),
                'ciudad': acreditacion.get('ciudad', ''),
            }).encode(),
        )
        for categoria in categorias
    })
    detalle = []
    for categoria, consulta in consultas.items():
        if consulta.parte['estado'] != 'DISPONIBLE':
            return consulta.parte
        candidatos = consulta.parte['datos']
        if not isinstance(candidatos, list):
            return parte_no_disponible('emparejamiento', 'RESPUESTA_INESPERADA')
        figura = next((c for c in candidatos if proveedor_id and c.get('proveedor_id') == proveedor_id), None)
        detalle.append({
            'categoria': categoria,
            'aparece': figura is not None,
            'nivel': figura.get('nivel') if figura else None,
        })
    return parte_disponible({'aparece': any(d['aparece'] for d in detalle), 'categorias': detalle})


@compuestos_bp.route('/proveedores/<id>/completo', methods=['GET'])
def proveedor_completo(id):
    """`id` es el de la acreditación: Acreditación busca por él, no por `proveedor_id`."""
    g.servicio_destino = 'compuesto'
    configuracion = current_app.config['BFF']
    consultas = en_paralelo({
        'acreditacion': partial(consultar, configuracion, 'acreditacion', f'/acreditaciones/{id}', raiz=True),
        'historial': partial(consultar, configuracion, 'acreditacion', f'/acreditaciones/{id}/eventos'),
    })
    parte = consultas['acreditacion'].parte
    if parte is not None and parte['estado'] == 'DISPONIBLE':
        datos = parte['datos']
        candidato = _candidato(configuracion, datos)
    else:
        datos = {}
        candidato = parte_no_disponible('acreditacion', 'DEPENDE_DE_ACREDITACION')
    consultas['candidato'] = Consulta(candidato)
    return consolidar(consultas, {'acreditacion_id': id, 'proveedor_id': datos.get('proveedor_id')})


def _salud(configuracion, servicio: str) -> dict:
    inicio = time.perf_counter()
    try:
        respuesta = cliente.llamar(
            configuracion.servicios[servicio], 'GET', '/health', timeout=configuracion.timeout_compuesto_s,
        )
    except cliente.FalloAtras as fallo:
        return {'estado': 'DOWN', 'motivo': fallo.motivo}
    if respuesta.codigo != 200:
        return {'estado': 'DOWN', 'motivo': 'RESPUESTA_INESPERADA'}
    return {'estado': 'UP', 'latencia_ms': round((time.perf_counter() - inicio) * 1000)}


@compuestos_bp.route('/estado-del-sistema', methods=['GET'])
def estado_del_sistema():
    """Siempre `200`: una vista de estado debe poder leerse justo cuando el sistema está mal."""
    g.servicio_destino = 'compuesto'
    configuracion = current_app.config['BFF']
    tareas = {nombre: partial(_salud, configuracion, nombre) for nombre in SERVICIOS_DE_ATRAS}
    tareas['sagas'] = partial(consultar, configuracion, 'saga-log', '/sagas/resumen')
    resultados = en_paralelo(tareas)
    componentes = {'bff': {'estado': 'UP'}, **{nombre: resultados[nombre] for nombre in SERVICIOS_DE_ATRAS}}
    general = 'OK' if all(c['estado'] == 'UP' for c in componentes.values()) else 'DEGRADADO'
    return jsonify({
        'correlation_id': correlacion.actual(),
        'estado_general': general,
        'componentes': componentes,
        'sagas': resultados['sagas'].parte,
    })


@compuestos_bp.route('/trabajos/asignacion', methods=['POST'])
def asignacion():
    """Crea el trabajo igual que `POST /trabajos` y agrega dónde seguir su saga."""
    respuesta = reenvio.reenviar('gestion-trabajos', 'POST', '/trabajos')
    trabajo_id = reenvio.id_creado(respuesta.get_data()) if respuesta.status_code == 202 else None
    if trabajo_id is None:
        return respuesta
    identificador = urllib.parse.quote(trabajo_id, safe='')
    respuesta.set_data(reenvio.agregar_campos_json(respuesta.get_data(), {
        'correlation_id': correlacion.actual(),
        'seguimiento_saga': f'/sagas/{identificador}',
        'seguimiento_completo': f'/trabajos/{identificador}/completo',
    }))
    correlacion.agregar_campos(trabajo_id=trabajo_id)
    return respuesta
