"""Lo único que la plantilla expone. Cada servicio agrega sus propias rutas."""
import os

from flask import Blueprint, jsonify

bp = Blueprint('salud', __name__)


@bp.route('/health')
def health():
    return jsonify({
        'status': 'up',
        'service': os.getenv('SERVICIO', 'servicio-plantilla'),
        'modo': os.getenv('MODO', 'api'),
    })
