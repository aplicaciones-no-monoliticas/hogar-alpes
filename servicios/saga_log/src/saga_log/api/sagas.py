"""ADAPTADOR de entrada síncrono. Contrato: `specs/002-saga-asignacion-trabajo/
contracts/saga-log-api.md`."""
from flask import Blueprint, jsonify, request

from saga_log.modulos.sagas.aplicacion.queries.obtener_resumen import ObtenerResumenSagas
from saga_log.modulos.sagas.aplicacion.queries.obtener_saga import ObtenerSaga
from saga_log.modulos.sagas.aplicacion.queries.obtener_sagas_por_estado import (
    ObtenerSagasPorEstado,
)
from saga_log.seedwork.aplicacion.queries import ejecutar_query

bp = Blueprint('sagas', __name__, url_prefix='/sagas')


@bp.route('/resumen', methods=['GET'])
def resumen():
    resultado = ejecutar_query(ObtenerResumenSagas())
    return jsonify(resultado.resultado), 200


@bp.route('', methods=['GET'])
def por_estado():
    estado = request.args.get('estado', 'EN_CURSO')
    resultado = ejecutar_query(ObtenerSagasPorEstado(estado=estado))
    return jsonify(resultado.resultado), 200


@bp.route('/<trabajo_id>', methods=['GET'])
def obtener(trabajo_id=None):
    resultado = ejecutar_query(ObtenerSaga(trabajo_id=trabajo_id))
    if not resultado.resultado:
        return jsonify({'error': 'No existe una transacción de saga para ese trabajo_id'}), 404
    return jsonify(resultado.resultado), 200
