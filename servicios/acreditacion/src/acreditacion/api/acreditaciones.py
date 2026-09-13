"""ADAPTADOR de entrada síncrono. El API no conoce el dominio: arma un comando
o una consulta y lo despacha. `SolicitarAcreditacion`, `AprobarAcreditacion` y
`RevocarAcreditacion` llegan tanto por HTTP como por `cmd-acreditacion`
(01-especificacion.md §4.4): los dos caminos ejecutan el mismo comando de
aplicación, así que se comportan igual."""
import logging

from flask import Blueprint, jsonify, request

from acreditacion.seedwork.aplicacion.comandos import ejecutar_comando
from acreditacion.seedwork.aplicacion.queries import ejecutar_query
from acreditacion.seedwork.dominio.excepciones import ReglaNegocioExcepcion

from acreditacion.modulos.acreditacion.aplicacion.comandos.aprobar_acreditacion import (
    AprobarAcreditacion,
)
from acreditacion.modulos.acreditacion.aplicacion.comandos.revocar_acreditacion import (
    RevocarAcreditacion,
)
from acreditacion.modulos.acreditacion.aplicacion.comandos.solicitar_acreditacion import (
    SolicitarAcreditacion,
)
from acreditacion.modulos.acreditacion.aplicacion.queries.obtener_acreditacion import (
    ObtenerAcreditacion,
)
from acreditacion.modulos.acreditacion.aplicacion.queries.obtener_eventos_acreditacion import (
    ObtenerEventosAcreditacion,
)
from acreditacion.modulos.acreditacion.dominio.excepciones import AcreditacionNoExisteExcepcion

logger = logging.getLogger(__name__)
bp = Blueprint('acreditaciones', __name__, url_prefix='/acreditaciones')


@bp.route('', methods=['POST'])
def solicitar():
    try:
        cuerpo = request.json or {}
        comando = SolicitarAcreditacion(
            proveedor_id=cuerpo.get('proveedor_id', ''),
            pais=cuerpo.get('pais', ''),
            ciudad=cuerpo.get('ciudad', ''),
            categorias=cuerpo.get('categorias', []),
            nivel=cuerpo.get('nivel', ''),
            vigencia_meses=int(cuerpo.get('vigencia_meses', 0)),
            motivo=cuerpo.get('motivo', ''),
            acreditacion_id=cuerpo.get('acreditacion_id', ''),
        )
        acreditacion_id = ejecutar_comando(comando)
        return jsonify({'id': acreditacion_id, 'estado': 'SOLICITADA'}), 202
    except ReglaNegocioExcepcion as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/<id>/aprobar', methods=['PUT'])
def aprobar(id=None):
    try:
        cuerpo = request.json or {}
        ejecutar_comando(AprobarAcreditacion(acreditacion_id=id, motivo=cuerpo.get('motivo', '')))
        return jsonify({'id': id, 'estado': 'ACREDITADA'}), 202
    except AcreditacionNoExisteExcepcion as e:
        return jsonify({'error': str(e)}), 404
    except ReglaNegocioExcepcion as e:
        return jsonify({'error': str(e)}), 409


@bp.route('/<id>/revocar', methods=['PUT'])
def revocar(id=None):
    try:
        cuerpo = request.json or {}
        ejecutar_comando(RevocarAcreditacion(acreditacion_id=id, motivo=cuerpo.get('motivo', '')))
        return jsonify({'id': id, 'estado': 'REVOCADA'}), 202
    except AcreditacionNoExisteExcepcion as e:
        return jsonify({'error': str(e)}), 404
    except ReglaNegocioExcepcion as e:
        return jsonify({'error': str(e)}), 409


@bp.route('/<id>', methods=['GET'])
def obtener(id=None):
    resultado = ejecutar_query(ObtenerAcreditacion(id=id))
    if not resultado.resultado:
        return jsonify({'error': 'Acreditación no encontrada'}), 404
    return jsonify(resultado.resultado), 200


@bp.route('/<id>/eventos', methods=['GET'])
def obtener_eventos(id=None):
    """El historial: la razón de ser del Event Sourcing aquí."""
    resultado = ejecutar_query(ObtenerEventosAcreditacion(id=id))
    if not resultado.resultado:
        return jsonify({'error': 'Acreditación no encontrada'}), 404
    return jsonify(resultado.resultado), 200
