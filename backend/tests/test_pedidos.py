from fastapi.testclient import TestClient

from tests.utils import CLIENTE1, CLIENTE2


def test_lista_solo_pedidos_del_cliente_del_mas_reciente_al_mas_antiguo(
    client: TestClient, datos: None
) -> None:
    respuesta = client.get("/api/v1/pedidos", headers=CLIENTE1)

    assert respuesta.status_code == 200
    pedidos = respuesta.json()
    assert [p["codigo"] for p in pedidos] == [
        "BY-000102",
        "BY-000101",
        "BY-000104",
        "BY-000103",
        "BY-000105",
    ]
    fechas = [p["creado_en"] for p in pedidos]
    assert fechas == sorted(fechas, reverse=True)


def test_otro_cliente_ve_sus_propios_pedidos(client: TestClient, datos: None) -> None:
    codigos = {p["codigo"] for p in client.get("/api/v1/pedidos", headers=CLIENTE2).json()}
    assert codigos == {"BY-000106", "BY-000107", "BY-000108"}


def test_detalle_con_items_y_montos(client: TestClient, datos: None) -> None:
    respuesta = client.get("/api/v1/pedidos/BY-000101", headers=CLIENTE1)

    assert respuesta.status_code == 200
    pedido = respuesta.json()
    assert pedido["total"] == "82.50"
    assert pedido["cantidad_productos"] == 5
    assert pedido["items"][0] == {
        "id": pedido["items"][0]["id"],
        "producto": "Combo Clásico (hamburguesa + papas + gaseosa)",
        "categoria": "combo",
        "cantidad": 2,
        "precio_unitario": "27.90",
        "subtotal": "55.80",
    }


def test_detalle_de_pedido_ajeno_responde_404(client: TestClient, datos: None) -> None:
    respuesta = client.get("/api/v1/pedidos/BY-000106", headers=CLIENTE1)
    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "pedido_no_encontrado"


def test_detalle_de_pedido_inexistente_responde_404(client: TestClient, datos: None) -> None:
    assert client.get("/api/v1/pedidos/BY-999999", headers=CLIENTE1).status_code == 404


def test_tipos_de_reclamo_disponibles_segun_estado_y_plazo(client: TestClient, datos: None) -> None:
    def tipos(codigo: str) -> list[str]:
        pedido = client.get(f"/api/v1/pedidos/{codigo}", headers=CLIENTE1).json()
        return pedido["tipos_reclamo_disponibles"]

    assert tipos("BY-000101") == [
        "producto_equivocado",
        "pedido_incompleto",
        "mal_estado",
        "demora",
    ]
    assert tipos("BY-000102") == ["demora"]  # en camino
    assert tipos("BY-000103") == []  # entregado hace 3 días
    assert tipos("BY-000105") == []  # cancelado
