from flask.testing import FlaskClient

from caja.formato import fecha_lima, soles


def test_buscar_pedido_existente_redirige_al_detalle(con_sesion: FlaskClient) -> None:
    respuesta = con_sesion.get("/pedidos/buscar", query_string={"codigo": " by-000101 "})
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/pedidos/BY-000101"


def test_buscar_pedido_inexistente_muestra_error(con_sesion: FlaskClient) -> None:
    respuesta = con_sesion.get("/pedidos/buscar", query_string={"codigo": "BY-999999"})
    assert respuesta.status_code == 404
    html = respuesta.get_data(as_text=True)
    assert 'id="mensaje-error"' in html
    assert "No existe el pedido BY-999999." in html


def test_buscar_sin_codigo_muestra_el_formulario(con_sesion: FlaskClient) -> None:
    respuesta = con_sesion.get("/pedidos/buscar")
    assert respuesta.status_code == 200
    assert 'id="buscar-codigo"' in respuesta.get_data(as_text=True)


def test_detalle_muestra_datos_e_items_con_ids_estables(con_sesion: FlaskClient) -> None:
    html = con_sesion.get("/pedidos/BY-000101").get_data(as_text=True)
    assert 'id="pedido-codigo">BY-000101<' in html
    assert 'id="pedido-estado" class="estado-entregado">ENTREGADO<' in html
    assert 'id="pedido-cliente">María Quispe<' in html
    assert 'id="pedido-total" class="num">S/ 46.30<' in html
    assert 'id="item-1"' in html
    assert 'id="item-2"' in html
    assert 'class="item-subtotal num">S/ 37.80<' in html


def test_detalle_de_pedido_inexistente(con_sesion: FlaskClient) -> None:
    respuesta = con_sesion.get("/pedidos/BY-000999")
    assert respuesta.status_code == 404
    assert "No existe el pedido BY-000999." in respuesta.get_data(as_text=True)


def test_no_tiene_api_json(con_sesion: FlaskClient) -> None:
    """SISCAJA solo responde HTML: el bot debe operarlo por la interfaz."""
    respuesta = con_sesion.get("/pedidos/BY-000101", headers={"Accept": "application/json"})
    assert respuesta.mimetype == "text/html"
    assert con_sesion.get("/api/pedidos/BY-000101").status_code == 404


def test_formatos() -> None:
    assert soles(4630) == "S/ 46.30"
    assert soles(123456) == "S/ 1,234.56"
    assert soles(5) == "S/ 0.05"
    assert fecha_lima("2026-10-27T17:45:00+00:00") == "27/10/2026 12:45"
    assert fecha_lima(None) == "-"
