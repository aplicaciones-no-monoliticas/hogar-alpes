"""ADAPTADOR de entrada síncrono. Operaciones no recibe comandos por HTTP
—`AbrirSeguimiento` y `RegistrarCambioEstado` son internos, disparados por el
consumidor—: este blueprint es solo consultas (lado de lectura del CQS)."""
from flask import Blueprint, jsonify, request

from operaciones.modulos.operaciones.aplicacion.queries.contar_seguimientos import (
    ContarEventosProcesados,
    ContarSeguimientos,
)
from operaciones.modulos.operaciones.aplicacion.queries.obtener_seguimiento import (
    ObtenerSeguimientoDeTrabajo,
)
from operaciones.seedwork.aplicacion.queries import ejecutar_query

bp = Blueprint('operaciones', __name__)


@bp.route('/seguimientos/<trabajo_id>', methods=['GET'])
def obtener_seguimiento(trabajo_id=None):
    resultado = ejecutar_query(ObtenerSeguimientoDeTrabajo(trabajo_id=trabajo_id))
    if not resultado.resultado:
        return jsonify({'error': 'Sin seguimiento para ese trabajo'}), 404
    return jsonify(resultado.resultado), 200


@bp.route('/seguimientos/conteo', methods=['GET'])
def contar_seguimientos():
    resultado = ejecutar_query(ContarSeguimientos(desde=request.args.get('desde', '')))
    return jsonify(resultado.resultado), 200


@bp.route('/eventos-procesados/conteo', methods=['GET'])
def contar_eventos_procesados():
    """Instrumento de CA-6.4 (0 duplicados) y CA-6.5 (0 huérfanos) — cuenta
    `eventos_procesados` por `resultado` (APLICADO · DUPLICADO · HUERFANO)."""
    resultado = ejecutar_query(
        ContarEventosProcesados(resultado=request.args.get('resultado', 'APLICADO'))
    )
    return jsonify(resultado.resultado), 200
