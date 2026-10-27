"""Constantes y ayudas compartidas por las pruebas."""

import json

from fastapi.testclient import TestClient
from httpx import Response

CLIENTE1 = {"X-Dev-User": "cliente1@burgerya.pe"}
CLIENTE2 = {"X-Dev-User": "cliente2@burgerya.pe"}

DESCRIPCION = "Me llegó una hamburguesa distinta a la que pedí."


def item_id(client: TestClient, pedido_codigo: str, indice: int = 0) -> int:
    """Id de un ítem del pedido (los ids dependen del orden en que se cargó la semilla)."""
    pedido = client.get(f"/api/v1/pedidos/{pedido_codigo}", headers=CLIENTE1).json()
    return int(pedido["items"][indice]["id"])


def crear_reclamo(
    client: TestClient,
    *,
    pedido_codigo: str = "BY-000101",
    tipo: str = "pedido_incompleto",
    descripcion: str = DESCRIPCION,
    items: list[dict[str, int]] | str | None = None,
    foto: tuple[str, bytes, str] | None = None,
    headers: dict[str, str] = CLIENTE1,
) -> Response:
    if items is None:
        items = [{"pedido_item_id": item_id(client, pedido_codigo), "cantidad_afectada": 1}]
    return client.post(
        "/api/v1/reclamos",
        headers=headers,
        data={
            "pedido_codigo": pedido_codigo,
            "tipo": tipo,
            "descripcion": descripcion,
            "items": items if isinstance(items, str) else json.dumps(items),
        },
        files={"foto": foto} if foto else None,
    )
