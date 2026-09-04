"""ADAPTADOR de entrada síncrono (puerto primario del hexágono).

El API no conoce el dominio: arma un comando o una consulta y lo despacha. Por
eso la ruta de escritura devuelve 202 y la de lectura 200 — CQS visible desde el
borde del sistema.
"""
import logging

from flask import Blueprint, jsonify, request

from gestion_trabajos.seedwork.aplicacion.comandos import ejecutar_comando
from gestion_trabajos.seedwork.aplicacion.queries import ejecutar_query
from gestion_trabajos.seedwork.dominio.excepciones import ReglaNegocioExcepcion
from gestion_trabajos.modulos.trabajos.aplicacion.comandos.cambiar_estado_trabajo import (
    CambiarEstadoTrabajo,
)
from gestion_trabajos.modulos.trabajos.aplicacion.comandos.crear_trabajo import (
    CrearTrabajo,
)
from gestion_trabajos.modulos.trabajos.aplicacion.mapeadores import (
    MapeadorTrabajoDTOJson,
)
from gestion_trabajos.modulos.trabajos.aplicacion.queries.obtener_trabajo import (
    ObtenerTrabajo,
)
from gestion_trabajos.modulos.trabajos.aplicacion.queries.obtener_trabajos_por_estado import (
    ObtenerTrabajosPorEstado,
)
from gestion_trabajos.modulos.operaciones.aplicacion.queries import (
    ObtenerSeguimientoDeTrabajo,
)

logger = logging.getLogger(__name__)
bp = Blueprint('trabajos', __name__, url_prefix='/trabajos')


@bp.route('', methods=['POST'])
def crear_trabajo():
    """Escenario 7: se acepta y se confirma de inmediato. El procesamiento
    aguas abajo se difiere."""
    try:
        cuerpo = request.json or {}
        comando = CrearTrabajo(
            canal=cuerpo.get('canal', 'MARKETPLACE'),
            partner_id=cuerpo.get('partner_id', ''),
            referencia_externa=cuerpo.get('referencia_externa', ''),
            categoria=cuerpo.get('categoria', ''),
            urgencia=cuerpo.get('urgencia', 'NORMAL'),
            pais=cuerpo.get('pais', ''),
            ciudad=cuerpo.get('ciudad', ''),
            direccion=cuerpo.get('direccion', ''),
            descripcion=cuerpo.get('descripcion', ''),
        )
        trabajo_id = ejecutar_comando(comando)
        return jsonify({'id': trabajo_id, 'estado': 'CREADO'}), 202
    except ReglaNegocioExcepcion as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/<id>', methods=['GET'])
def obtener_trabajo(id=None):
    resultado = ejecutar_query(ObtenerTrabajo(id=id))
    if not resultado.resultado:
        return jsonify({'error': 'Trabajo no encontrado'}), 404
    return jsonify(MapeadorTrabajoDTOJson().dto_a_externo(resultado.resultado)), 200


@bp.route('', methods=['GET'])
def obtener_por_estado():
    estado = request.args.get('estado', 'CREADO')
    resultado = ejecutar_query(ObtenerTrabajosPorEstado(estado=estado))
    mapeador = MapeadorTrabajoDTOJson()
    return jsonify([mapeador.dto_a_externo(d) for d in resultado.resultado]), 200


@bp.route('/<id>/estado', methods=['PUT'])
def cambiar_estado(id=None):
    """Escenario 3: el estado nuevo se valida en el objeto valor EstadoTrabajo."""
    try:
        cuerpo = request.json or {}
        ejecutar_comando(CambiarEstadoTrabajo(trabajo_id=id, estado=cuerpo.get('estado', '')))
        return jsonify({'id': id, 'estado': cuerpo.get('estado')}), 202
    except ReglaNegocioExcepcion as e:
        return jsonify({'error': str(e)}), 409


@bp.route('/<id>/seguimiento', methods=['GET'])
def obtener_seguimiento(id=None):
    """Lee el módulo `operaciones`: prueba de que el evento de dominio cruzó."""
    resultado = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id=id))
    if not resultado.resultado:
        return jsonify({'error': 'Sin seguimiento operativo'}), 404
    return jsonify(resultado.resultado), 200
