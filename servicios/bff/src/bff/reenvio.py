"""Reenvío fiel: misma ruta, cuerpo y código que si se llamara directo al servicio."""
import json

from flask import Response, current_app, g, request

from . import cliente, correlacion, errores


def agregar_campos_json(cuerpo: bytes, campos: dict) -> bytes:
    """Suma `campos` a un cuerpo JSON que sea un objeto, sin pisar ni quitar nada; si no lo es, lo devuelve intacto."""
    try:
        objeto = json.loads(cuerpo)
    except ValueError:
        return cuerpo
    if not isinstance(objeto, dict):
        return cuerpo
    for clave, valor in campos.items():
        objeto.setdefault(clave, valor)
    return json.dumps(objeto, ensure_ascii=False).encode('utf-8')


def id_creado(cuerpo: bytes) -> str | None:
    """El `id` de una respuesta de creación, o `None` si el cuerpo no es un objeto JSON con `id`."""
    try:
        objeto = json.loads(cuerpo)
    except ValueError:
        return None
    if isinstance(objeto, dict) and objeto.get('id'):
        return str(objeto['id'])
    return None


def respuesta_de_fallo(fallo: cliente.FalloAtras):
    if fallo.motivo == 'ERROR_INTERNO_UPSTREAM':
        return errores.error_upstream(fallo.servicio, fallo.status)
    return errores.servicio_no_disponible(fallo.servicio, fallo.motivo)


def a_respuesta_flask(respuesta: cliente.Respuesta) -> Response:
    salida = Response(respuesta.cuerpo, status=respuesta.codigo)
    salida.headers.pop('Content-Type', None)
    if respuesta.tipo_contenido:
        salida.headers['Content-Type'] = respuesta.tipo_contenido
    if respuesta.location:
        salida.headers['Location'] = respuesta.location
    return salida


def _anotar_creacion(salida: Response, regla) -> None:
    """Una creación que inicia una saga devuelve también el identificador de correlación en el cuerpo."""
    cuerpo = salida.get_data()
    creado = id_creado(cuerpo)
    if creado is None:
        return
    salida.set_data(agregar_campos_json(cuerpo, {'correlation_id': correlacion.actual()}))
    if regla.campo_id:
        correlacion.agregar_campos(**{regla.campo_id: creado})


def reenviar(servicio: str, metodo: str, ruta: str, regla=None, argumentos=None) -> Response:
    configuracion = current_app.config['BFF']
    g.servicio_destino = servicio
    if regla is not None and regla.campo_id and not regla.agrega_correlacion and 'id' in (argumentos or {}):
        correlacion.agregar_campos(**{regla.campo_id: argumentos['id']})
    try:
        respuesta = cliente.llamar(
            configuracion.servicios[servicio],
            metodo,
            ruta,
            consulta=request.query_string,
            cuerpo=request.get_data() or None,
            cabeceras={'Content-Type': request.headers.get('Content-Type'), 'Accept': request.headers.get('Accept')},
            timeout=configuracion.timeout_reenvio_s,
        )
    except cliente.FalloAtras as fallo:
        return respuesta_de_fallo(fallo)
    salida = a_respuesta_flask(respuesta)
    if regla is not None and regla.agrega_correlacion and 200 <= respuesta.codigo < 300:
        _anotar_creacion(salida, regla)
    return salida


def crear_vista(regla):
    def vista(**argumentos):
        return reenviar(regla.servicio, regla.metodo, request.path, regla, argumentos)

    return vista
