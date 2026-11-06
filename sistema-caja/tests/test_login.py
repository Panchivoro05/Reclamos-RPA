from flask.testing import FlaskClient

from tests.conftest import CLAVE, USUARIO, iniciar_sesion, token_csrf


def test_login_correcto_redirige_a_buscar(cliente: FlaskClient) -> None:
    respuesta = iniciar_sesion(cliente, USUARIO, CLAVE)
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/pedidos/buscar"

    pagina = cliente.get("/pedidos/buscar").get_data(as_text=True)
    assert f'id="operador-actual">{USUARIO}<' in pagina


def test_login_con_clave_incorrecta(cliente: FlaskClient) -> None:
    respuesta = iniciar_sesion(cliente, USUARIO, "otra-clave")
    assert respuesta.status_code == 401
    assert "Usuario o clave incorrectos." in respuesta.get_data(as_text=True)


def test_login_con_usuario_inexistente(cliente: FlaskClient) -> None:
    respuesta = iniciar_sesion(cliente, "nadie", CLAVE)
    assert respuesta.status_code == 401


def test_login_sin_token_csrf_se_rechaza(cliente: FlaskClient) -> None:
    respuesta = cliente.post("/login", data={"usuario": USUARIO, "clave": CLAVE})
    assert respuesta.status_code == 400


def test_sin_sesion_redirige_al_login_y_vuelve(cliente: FlaskClient) -> None:
    respuesta = cliente.get("/pedidos/BY-000101")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].startswith("/login?siguiente=")

    respuesta = iniciar_sesion(cliente, USUARIO, CLAVE, siguiente="/pedidos/BY-000101")
    assert respuesta.headers["Location"] == "/pedidos/BY-000101"


def test_no_redirige_a_sitios_externos(cliente: FlaskClient) -> None:
    respuesta = iniciar_sesion(cliente, USUARIO, CLAVE, siguiente="//malicioso.com")
    assert respuesta.headers["Location"] == "/pedidos/buscar"


def test_logout_cierra_la_sesion(con_sesion: FlaskClient) -> None:
    token = token_csrf(con_sesion, "/pedidos/buscar")
    respuesta = con_sesion.post("/logout", data={"csrf_token": token})
    assert respuesta.status_code == 302
    assert con_sesion.get("/pedidos/buscar").status_code == 302
