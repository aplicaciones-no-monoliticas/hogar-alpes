from flask import Blueprint, jsonify

bp = Blueprint('salud', __name__)


@bp.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'up', 'service': 'bff'})
