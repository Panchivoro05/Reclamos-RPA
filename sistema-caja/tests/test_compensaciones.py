import re

from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from caja import db
from tests.conftest import token_csrf

MOTIVO = "Cliente recibió una hamburguesa equivocada."


def compensar(
    cliente: FlaskClient,
    tipo: str,
    monto: str = "",
    motivo: str = MOTIVO,
    codigo: str = "BY-000101",
) -> TestResponse:
    ruta = f"/pedidos/{codigo}/compensar"
    datos = {
        "csrf_token": token_csrf(cliente, ruta),
        "tipo": tipo,
        "monto": monto,
        "motivo": motivo,
    }
    return cliente.post(ruta, data=datos)


def numero_en(respuesta: TestResponse) -> str:
    encontrado = re.search(r"/compensaciones/(CMP-\d{6})$", respuesta.headers["Location"])
    assert encontrado, respuesta.headers["Location"]
    return encontrado.group(1)


def test_reembolso_parcial_genera_numero_y_comprobante(con_sesion: FlaskClient) -> None:
    respuesta = compensar(con_sesion, "reembolso_parcial", "18.90")
    assert respuesta.status_code == 302
    assert numero_en(respuesta) == "CMP-000001"

    html = con_sesion.get("/compensaciones/CMP-000001").get_data(as_text=True)
    assert 'id="mensaje-exito"' in html
    assert 'id="numero-operacion">CMP-000001<' in html
    assert 'id="op-monto">S/ 18.90<' in html
    assert 'data-tipo="reembolso_parcial"' in html


def test_numeros_correlativos(con_sesion: FlaskClient) -> None:
    assert numero_en(compensar(con_sesion, "cupon", "10")) == "CMP-000001"
    assert numero_en(compensar(con_sesion, "reenvio")) == "CMP-000002"


def test_reembolso_parcial_con_monto_excedido(con_sesion: FlaskClient) -> None:
    respuesta = compensar(con_sesion, "reembolso_parcial", "46.31")
    assert respuesta.status_code == 422
    html = respuesta.get_data(as_text=True)
    assert 'id="mensaje-error"' in html
    assert "Monto excedido: el maximo reembolsable es S/ 46.30." in html
    # Conserva lo ingresado para corregirlo
    assert 'value="46.31"' in html


def test_saldo_descuenta_reembolsos_anteriores(con_sesion: FlaskClient) -> None:
    compensar(con_sesion, "reembolso_parcial", "40")
    respuesta = compensar(con_sesion, "reembolso_parcial", "6.31")
    assert "el maximo reembolsable es S/ 6.30." in respuesta.get_data(as_text=True)

    html = con_sesion.get("/pedidos/BY-000101").get_data(as_text=True)
    assert 'id="saldo-reembolsable">S/ 6.30<' in html


def test_reembolso_total_usa_el_saldo_e_ignora_el_monto(con_sesion: FlaskClient) -> None:
    compensar(con_sesion, "reembolso_parcial", "10")
    numero = numero_en(compensar(con_sesion, "reembolso_total", "999"))
    html = con_sesion.get(f"/compensaciones/{numero}").get_data(as_text=True)
    assert 'id="op-monto">S/ 36.30<' in html

    respuesta = compensar(con_sesion, "reembolso_total")
    assert respuesta.status_code == 422
    assert "ya fue reembolsado por completo" in respuesta.get_data(as_text=True)


def test_reenvio_tiene_monto_cero(con_sesion: FlaskClient) -> None:
    numero = numero_en(compensar(con_sesion, "reenvio", "25"))
    html = con_sesion.get(f"/compensaciones/{numero}").get_data(as_text=True)
    assert 'id="op-monto">S/ 0.00<' in html


def test_cupon_no_descuenta_saldo_ni_supera_el_total(con_sesion: FlaskClient) -> None:
    compensar(con_sesion, "cupon", "20")
    html = con_sesion.get("/pedidos/BY-000101").get_data(as_text=True)
    assert 'id="saldo-reembolsable">S/ 46.30<' in html

    respuesta = compensar(con_sesion, "cupon", "50")
    assert respuesta.status_code == 422
    assert "el cupon no puede superar el total del pedido" in respuesta.get_data(as_text=True)


def test_montos_invalidos(con_sesion: FlaskClient) -> None:
    casos = {
        "": "Ingrese el monto.",
        "abc": "Monto invalido: abc.",
        "-5": "El monto debe ser mayor que cero.",
        "0": "El monto debe ser mayor que cero.",
        "1.005": "El monto admite como maximo 2 decimales.",
        "NaN": "Monto invalido: NaN.",
    }
    for monto, mensaje in casos.items():
        respuesta = compensar(con_sesion, "reembolso_parcial", monto)
        assert respuesta.status_code == 422, monto
        assert mensaje in respuesta.get_data(as_text=True), monto


def test_acepta_formato_peruano_del_monto(con_sesion: FlaskClient) -> None:
    numero = numero_en(compensar(con_sesion, "reembolso_parcial", "S/ 12,50"))
    html = con_sesion.get(f"/compensaciones/{numero}").get_data(as_text=True)
    assert 'id="op-monto">S/ 12.50<' in html


def test_motivo_y_tipo_obligatorios(con_sesion: FlaskClient) -> None:
    respuesta = compensar(con_sesion, "reenvio", motivo="corto")
    assert "al menos 10 caracteres" in respuesta.get_data(as_text=True)
    respuesta = compensar(con_sesion, "regalo", "5")
    assert "Seleccione el tipo de compensacion." in respuesta.get_data(as_text=True)


def test_pedido_inexistente(con_sesion: FlaskClient) -> None:
    respuesta = con_sesion.get("/pedidos/BY-999999/compensar")
    assert respuesta.status_code == 404
    assert "No existe el pedido BY-999999." in respuesta.get_data(as_text=True)


def test_pedido_cancelado_no_admite_compensaciones(app: Flask, con_sesion: FlaskClient) -> None:
    conexion = db.conectar(app.config["DB_PATH"])
    conexion.execute("UPDATE pedidos SET estado = 'cancelado' WHERE codigo = 'BY-000101'")
    conexion.commit()
    conexion.close()

    respuesta = compensar(con_sesion, "cupon", "5")
    assert respuesta.status_code == 422
    assert "esta cancelado" in respuesta.get_data(as_text=True)


def test_historial_y_detalle_listan_las_compensaciones(con_sesion: FlaskClient) -> None:
    html = con_sesion.get("/compensaciones").get_data(as_text=True)
    assert 'id="sin-compensaciones"' in html

    compensar(con_sesion, "cupon", "10")
    compensar(con_sesion, "reenvio")
    html = con_sesion.get("/compensaciones").get_data(as_text=True)
    assert 'id="comp-CMP-000001"' in html
    assert 'id="comp-CMP-000002"' in html

    html = con_sesion.get("/pedidos/BY-000101").get_data(as_text=True)
    assert 'id="comp-CMP-000002"' in html
    assert 'id="btn-compensar"' in html


def test_comprobante_inexistente(con_sesion: FlaskClient) -> None:
    assert con_sesion.get("/compensaciones/CMP-999999").status_code == 404


def test_registrar_requiere_sesion(cliente: FlaskClient) -> None:
    respuesta = cliente.get("/pedidos/BY-000101/compensar")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].startswith("/login")
