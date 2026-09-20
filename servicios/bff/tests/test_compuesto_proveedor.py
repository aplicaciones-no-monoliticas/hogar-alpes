"""GET /proveedores/{id}/completo (FR-014, research R5/H3). `{id}` es el de la acreditación."""
ACREDITACION = {
    'id': 'a1', 'proveedor_id': 'p-77', 'pais': 'CO', 'ciudad': 'Bogota',
    'categorias': ['PLOMERIA', 'ELECTRICIDAD'], 'nivel': 'SENIOR', 'estado': 'ACREDITADA',
    'vigente_hasta': '2027-01-01', 'version': 2,
}
EVENTOS = [{'tipo': 'AcreditacionSolicitada'}, {'tipo': 'AcreditacionAprobada'}]
PLOMERIA = 'categoria=PLOMERIA&pais=CO&ciudad=Bogota'
ELECTRICIDAD = 'categoria=ELECTRICIDAD&pais=CO&ciudad=Bogota'


def _preparar(atras):
    atras['acreditacion'].responder('GET', '/acreditaciones/a1', 200, ACREDITACION)
    atras['acreditacion'].responder('GET', '/acreditaciones/a1/eventos', 200, EVENTOS)
    atras['emparejamiento'].responder('GET', '/candidatos', 200, [])


def _candidatos(atras, consulta, lista):
    atras['emparejamiento'].responder('GET', '/candidatos', 200, lista, consulta=consulta)


def test_consulta_los_candidatos_una_vez_por_categoria_con_pais_y_ciudad(cliente, atras):
    _preparar(atras)

    respuesta = cliente.get('/proveedores/a1/completo')

    assert respuesta.status_code == 200
    consultas = sorted(r['consulta'] for r in atras['emparejamiento'].recibidas)
    assert consultas == [ELECTRICIDAD, PLOMERIA]
    assert [r['ruta'] for r in atras['acreditacion'].recibidas].count('/acreditaciones/a1') == 1
    cuerpo = respuesta.get_json()
    assert cuerpo['acreditacion_id'] == 'a1'
    assert cuerpo['proveedor_id'] == 'p-77'
    assert cuerpo['correlation_id'] == respuesta.headers['X-Correlation-Id']
    assert cuerpo['partes']['acreditacion'] == {'estado': 'DISPONIBLE', 'datos': ACREDITACION}
    assert cuerpo['partes']['historial'] == {'estado': 'DISPONIBLE', 'datos': EVENTOS}


def test_aparece_si_el_proveedor_figura_en_todas_las_categorias(cliente, atras):
    _preparar(atras)
    figura = [{'proveedor_id': 'p-77', 'nivel': 'SENIOR', 'vigente_hasta': '2027-01-01'}]
    _candidatos(atras, PLOMERIA, figura)
    _candidatos(atras, ELECTRICIDAD, figura)

    candidato = cliente.get('/proveedores/a1/completo').get_json()['partes']['candidato']

    assert candidato['estado'] == 'DISPONIBLE'
    assert candidato['datos']['aparece'] is True
    assert candidato['datos']['categorias'] == [
        {'categoria': 'PLOMERIA', 'aparece': True, 'nivel': 'SENIOR'},
        {'categoria': 'ELECTRICIDAD', 'aparece': True, 'nivel': 'SENIOR'},
    ]


def test_aparece_si_figura_en_solo_una_de_las_categorias(cliente, atras):
    _preparar(atras)
    _candidatos(atras, PLOMERIA, [{'proveedor_id': 'otro', 'nivel': 'JUNIOR', 'vigente_hasta': '2027-01-01'}])
    _candidatos(atras, ELECTRICIDAD, [{'proveedor_id': 'p-77', 'nivel': 'MASTER', 'vigente_hasta': '2027-01-01'}])

    candidato = cliente.get('/proveedores/a1/completo').get_json()['partes']['candidato']

    assert candidato['datos']['aparece'] is True
    assert candidato['datos']['categorias'] == [
        {'categoria': 'PLOMERIA', 'aparece': False, 'nivel': None},
        {'categoria': 'ELECTRICIDAD', 'aparece': True, 'nivel': 'MASTER'},
    ]


def test_no_aparece_si_no_figura_en_ninguna_categoria(cliente, atras):
    _preparar(atras)
    otro = [{'proveedor_id': 'otro', 'nivel': 'JUNIOR', 'vigente_hasta': '2027-01-01'}]
    _candidatos(atras, PLOMERIA, otro)
    _candidatos(atras, ELECTRICIDAD, [])

    candidato = cliente.get('/proveedores/a1/completo').get_json()['partes']['candidato']

    assert candidato['estado'] == 'DISPONIBLE'
    assert candidato['datos']['aparece'] is False
    assert [c['aparece'] for c in candidato['datos']['categorias']] == [False, False]


def test_si_la_acreditacion_no_existe_el_404_llega_tal_cual_y_sin_partes(cliente, atras):
    cuerpo = '{"error": "Acreditación no encontrada"}'.encode()
    atras['acreditacion'].responder('GET', '/acreditaciones/a1', 404, cuerpo)
    atras['acreditacion'].responder('GET', '/acreditaciones/a1/eventos', 404, cuerpo)

    respuesta = cliente.get('/proveedores/a1/completo')

    assert respuesta.status_code == 404
    assert respuesta.data == cuerpo
    assert b'partes' not in respuesta.data
    assert atras['emparejamiento'].recibidas == []


def test_con_acreditacion_caida_las_tres_partes_fallan_y_la_respuesta_es_503(cliente, atras):
    atras['acreditacion'].detener()

    respuesta = cliente.get('/proveedores/a1/completo')

    assert respuesta.status_code == 503
    assert respuesta.get_json()['servicio'] == ['acreditacion']


def test_con_emparejamiento_caido_solo_falla_la_parte_del_candidato(cliente, atras):
    _preparar(atras)
    atras['emparejamiento'].detener()

    respuesta = cliente.get('/proveedores/a1/completo')

    assert respuesta.status_code == 200
    partes = respuesta.get_json()['partes']
    assert partes['acreditacion']['estado'] == 'DISPONIBLE'
    assert partes['historial']['estado'] == 'DISPONIBLE'
    assert partes['candidato'] == {
        'estado': 'NO_DISPONIBLE', 'servicio': 'emparejamiento', 'motivo': 'CONEXION_RECHAZADA',
    }


def test_si_la_acreditacion_falla_pero_el_historial_no_no_se_consulta_a_candidatos(cliente, atras):
    atras['acreditacion'].responder('GET', '/acreditaciones/a1', 500, b'boom', tipo='text/plain')
    atras['acreditacion'].responder('GET', '/acreditaciones/a1/eventos', 200, EVENTOS)

    respuesta = cliente.get('/proveedores/a1/completo')

    assert respuesta.status_code == 200
    partes = respuesta.get_json()['partes']
    assert partes['acreditacion'] == {
        'estado': 'NO_DISPONIBLE', 'servicio': 'acreditacion', 'motivo': 'ERROR_INTERNO_UPSTREAM',
    }
    assert partes['historial']['estado'] == 'DISPONIBLE'
    assert partes['candidato'] == {
        'estado': 'NO_DISPONIBLE', 'servicio': 'acreditacion', 'motivo': 'DEPENDE_DE_ACREDITACION',
    }
    assert atras['emparejamiento'].recibidas == []
