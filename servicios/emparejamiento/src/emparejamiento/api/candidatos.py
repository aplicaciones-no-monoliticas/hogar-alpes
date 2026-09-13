"""ADAPTADOR de entrada síncrono. Emparejamiento no recibe comandos por HTTP
—`EmparejarTrabajo` es interno, disparado por el consumidor regional—: este
blueprint es solo consultas (lado de lectura del CQS)."""
from flask import Blueprint, jsonify, request

from emparejamiento.seedwork.aplicacion.queries import ejecutar_query

from emparejamiento.modulos.emparejamiento.aplicacion.queries.obtener_candidatos import (
    ObtenerCandidatos,
)
from emparejamiento.modulos.emparejamiento.aplicacion.queries.obtener_emparejamiento import (
    ObtenerEmparejamiento,
)

bp = Blueprint('emparejamiento', __name__)


@bp.route('/candidatos', methods=['GET'])
def obtener_candidatos():
    resultado = ejecutar_query(ObtenerCandidatos(
        categoria=request.args.get('categoria', ''),
        pais=request.args.get('pais', ''),
        ciudad=request.args.get('ciudad', ''),
    ))
    return jsonify(resultado.resultado), 200


@bp.route('/emparejamientos/<trabajo_id>', methods=['GET'])
def obtener_emparejamiento(trabajo_id=None):
    resultado = ejecutar_query(ObtenerEmparejamiento(trabajo_id=trabajo_id))
    if not resultado.resultado:
        return jsonify({'error': 'Sin emparejamiento para ese trabajo'}), 404
    return jsonify(resultado.resultado), 200
