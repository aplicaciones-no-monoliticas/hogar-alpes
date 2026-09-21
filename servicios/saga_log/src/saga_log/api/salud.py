"""`GET /health` — sin dependencias externas en la respuesta (no consulta el
broker ni bloquea si Pulsar está caído). Forma fijada por
`specs/002-saga-asignacion-trabajo/contracts/saga-log-api.md`.
"""
from flask import Blueprint, jsonify

bp = Blueprint('salud', __name__)


@bp.route('/health')
def health():
    return jsonify({'estado': 'UP', 'servicio': 'saga-log'})
