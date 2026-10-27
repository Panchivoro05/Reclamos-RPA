import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import ActorEvento, EstadoReclamo, Reclamo, ReclamoEvento
from app.services import cola, reclamos
from tests.utils import CLIENTE1, CLIENTE2, crear_reclamo, item_id

# ---------- Reclamo válido ----------


def test_reclamo_valido_queda_recibido_con_su_primer_evento(
    client: TestClient,
    datos: None,
    foto_png: bytes,
    carpeta_fotos: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encolados: list[str] = []
    monkeypatch.setattr(cola.logger, "info", lambda *args: encolados.append(args[1]))

    respuesta = crear_reclamo(client, tipo="mal_estado", foto=("foto.png", foto_png, "image/png"))

    assert respuesta.status_code == 201, respuesta.text
    reclamo = respuesta.json()
    assert re.fullmatch(r"RC-\d{4}-000001", reclamo["codigo"])
    assert reclamo["estado"] == "recibido"
    assert reclamo["pedido_codigo"] == "BY-000101"
    assert reclamo["items"][0]["cantidad_afectada"] == 1
    assert [e["estado"] for e in reclamo["eventos"]] == ["recibido"]
    assert reclamo["eventos"][0]["mensaje"].startswith("Recibimos tu reclamo")
    assert reclamo["eventos"][0]["actor"] == "cliente"
    # La foto se guardó y se encoló el reclamo.
    nombre_foto = reclamo["foto_url"].rsplit("/", 1)[1]
    assert (carpeta_fotos / nombre_foto).read_bytes() == foto_png
    assert encolados == [reclamo["codigo"]]


def test_codigos_de_reclamo_son_correlativos(client: TestClient, datos: None) -> None:
    primero = crear_reclamo(client, tipo="pedido_incompleto").json()["codigo"]
    segundo = crear_reclamo(client, pedido_codigo="BY-000102", tipo="demora", items=[])
    assert primero.endswith("-000001")
    assert segundo.json()["codigo"].endswith("-000002")


def test_demora_de_pedido_en_camino_sin_items_ni_foto(client: TestClient, datos: None) -> None:
    respuesta = crear_reclamo(client, pedido_codigo="BY-000102", tipo="demora", items=[])
    assert respuesta.status_code == 201
    assert respuesta.json()["foto_url"] is None


# ---------- Estado del pedido y plazo ----------


def test_fuera_de_plazo(client: TestClient, datos: None) -> None:
    respuesta = crear_reclamo(client, pedido_codigo="BY-000103")
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "fuera_de_plazo"
    assert "24 horas" in respuesta.json()["detail"]


def test_plazo_es_configurable(
    client: TestClient, datos: None, configurar: Callable[..., None]
) -> None:
    configurar(reclamo_plazo_horas=100)
    assert crear_reclamo(client, pedido_codigo="BY-000103").status_code == 201


def test_pedido_cancelado_no_admite_reclamos(client: TestClient, datos: None) -> None:
    respuesta = crear_reclamo(client, pedido_codigo="BY-000105", tipo="demora", items=[])
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "pedido_no_reclamable"


def test_pedido_en_camino_solo_admite_demora(client: TestClient, datos: None) -> None:
    respuesta = crear_reclamo(client, pedido_codigo="BY-000102", tipo="pedido_incompleto")
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "pedido_no_reclamable"


def test_pedido_ajeno_responde_404(client: TestClient, datos: None) -> None:
    respuesta = crear_reclamo(client, pedido_codigo="BY-000106", tipo="demora", items=[])
    assert respuesta.status_code == 404


# ---------- Ítems ----------


def test_item_de_otro_pedido(client: TestClient, datos: None) -> None:
    ajeno = item_id(client, "BY-000104")
    respuesta = crear_reclamo(client, items=[{"pedido_item_id": ajeno, "cantidad_afectada": 1}])
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "item_no_pertenece"


def test_cantidad_excedida(client: TestClient, datos: None) -> None:
    combo = item_id(client, "BY-000101")  # se pidieron 2
    respuesta = crear_reclamo(client, items=[{"pedido_item_id": combo, "cantidad_afectada": 3}])
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "cantidad_excedida"
    assert "Pediste 2" in respuesta.json()["detail"]


def test_item_repetido(client: TestClient, datos: None) -> None:
    combo = item_id(client, "BY-000101")
    items = [{"pedido_item_id": combo, "cantidad_afectada": 1}] * 2
    respuesta = crear_reclamo(client, items=items)
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "item_repetido"


def test_items_obligatorios_salvo_en_demora(client: TestClient, datos: None) -> None:
    respuesta = crear_reclamo(client, tipo="pedido_incompleto", items=[])
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "items_requeridos"


def test_items_con_json_invalido_responde_400(client: TestClient, datos: None) -> None:
    respuesta = crear_reclamo(client, items="[{")
    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "items_invalidos"


def test_items_con_cantidad_cero(client: TestClient, datos: None) -> None:
    combo = item_id(client, "BY-000101")
    respuesta = crear_reclamo(client, items=[{"pedido_item_id": combo, "cantidad_afectada": 0}])
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "items_invalidos"


# ---------- Duplicados ----------


def test_reclamo_duplicado_responde_409(client: TestClient, datos: None) -> None:
    assert crear_reclamo(client).status_code == 201
    respuesta = crear_reclamo(client)
    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "reclamo_duplicado"


def test_mismo_pedido_admite_reclamo_de_otro_tipo(client: TestClient, datos: None) -> None:
    assert crear_reclamo(client, tipo="pedido_incompleto").status_code == 201
    assert crear_reclamo(client, tipo="demora", items=[]).status_code == 201


def test_se_puede_reclamar_de_nuevo_cuando_el_anterior_se_resolvio(
    client: TestClient, db: Session, datos: None
) -> None:
    assert crear_reclamo(client).status_code == 201
    db.execute(update(Reclamo).values(estado=EstadoReclamo.RESUELTO))
    db.commit()
    assert crear_reclamo(client).status_code == 201


def test_indice_unico_frena_duplicados_simultaneos(
    client: TestClient,
    datos: None,
    foto_png: bytes,
    carpeta_fotos: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simula dos peticiones simultáneas: la validación previa no ve el primer reclamo,
    pero el índice único parcial de la base lo rechaza igual."""
    foto = ("foto.png", foto_png, "image/png")
    assert crear_reclamo(client, tipo="mal_estado", foto=foto).status_code == 201
    monkeypatch.setattr(reclamos, "_tipos_abiertos", lambda *_: set())

    respuesta = crear_reclamo(client, tipo="mal_estado", foto=foto)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "reclamo_duplicado"
    # La foto del intento fallido se borró: solo queda la del primero.
    assert len(list(carpeta_fotos.iterdir())) == 1


# ---------- Foto ----------


@pytest.mark.parametrize("tipo", ["producto_equivocado", "mal_estado"])
def test_foto_obligatoria_faltante(client: TestClient, datos: None, tipo: str) -> None:
    respuesta = crear_reclamo(client, tipo=tipo)
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "foto_requerida"


def test_foto_con_formato_invalido(client: TestClient, datos: None, carpeta_fotos: Path) -> None:
    # Dice ser JPG, pero el contenido no es una imagen.
    foto = ("foto.jpg", b"esto no es una imagen", "image/jpeg")
    respuesta = crear_reclamo(client, tipo="mal_estado", foto=foto)
    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "foto_formato_invalido"
    assert not carpeta_fotos.exists()


def test_foto_demasiado_grande(
    client: TestClient, datos: None, foto_png: bytes, configurar: Callable[..., None]
) -> None:
    configurar(foto_max_bytes=len(foto_png) - 1)
    respuesta = crear_reclamo(client, tipo="mal_estado", foto=("foto.png", foto_png, "image/png"))
    assert respuesta.status_code == 413
    assert respuesta.json()["codigo"] == "foto_muy_grande"


@pytest.mark.parametrize(
    ("contenido", "extension"),
    [
        (b"\xff\xd8\xff\xe0" + b"0" * 20, "jpg"),
        (b"\x89PNG\r\n\x1a\n" + b"0" * 20, "png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
        (b"GIF89a" + b"0" * 20, None),
        (b"", None),
    ],
)
def test_detectar_formato_imagen(contenido: bytes, extension: str | None) -> None:
    assert reclamos.detectar_formato_imagen(contenido) == extension


# ---------- Validación del formulario ----------


def test_errores_de_formulario_en_espanol(client: TestClient, datos: None) -> None:
    respuesta = crear_reclamo(client, tipo="otro", descripcion="corta", items=[])
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "validacion"
    errores = {e["campo"]: e["mensaje"] for e in cuerpo["errores"]}
    assert errores["descripcion"] == "Debe tener al menos 10 caracteres."
    assert "'demora'" in errores["tipo"]
    assert " or " not in errores["tipo"]


# ---------- Consulta ----------


def test_lista_y_detalle_solo_del_cliente(client: TestClient, datos: None) -> None:
    codigo = crear_reclamo(client).json()["codigo"]
    crear_reclamo(client, pedido_codigo="BY-000102", tipo="demora", items=[])

    lista = client.get("/api/v1/reclamos", headers=CLIENTE1).json()
    assert [r["pedido_codigo"] for r in lista] == ["BY-000102", "BY-000101"]
    assert client.get("/api/v1/reclamos", headers=CLIENTE2).json() == []

    detalle = client.get(f"/api/v1/reclamos/{codigo}", headers=CLIENTE1)
    assert detalle.status_code == 200
    assert detalle.json()["items"][0]["producto"].startswith("Combo Clásico")
    assert client.get(f"/api/v1/reclamos/{codigo}", headers=CLIENTE2).status_code == 404


def test_eventos_en_orden_cronologico(client: TestClient, db: Session, datos: None) -> None:
    codigo = crear_reclamo(client).json()["codigo"]
    reclamo = db.scalars(select(Reclamo).where(Reclamo.codigo == codigo)).one()
    db.add(
        ReclamoEvento(
            reclamo_id=reclamo.id,
            estado=EstadoReclamo.EN_VALIDACION,
            mensaje="Estamos validando tu pedido.",
            actor=ActorEvento.SISTEMA,
        )
    )
    db.commit()

    eventos = client.get(f"/api/v1/reclamos/{codigo}", headers=CLIENTE1).json()["eventos"]
    assert [e["estado"] for e in eventos] == ["recibido", "en_validacion"]


def test_reclamo_ya_no_aparece_como_tipo_disponible(client: TestClient, datos: None) -> None:
    crear_reclamo(client, tipo="pedido_incompleto")
    pedido = client.get("/api/v1/pedidos/BY-000101", headers=CLIENTE1).json()
    assert "pedido_incompleto" not in pedido["tipos_reclamo_disponibles"]


# ---------- Fotos ----------


def test_foto_solo_la_ve_el_dueno(client: TestClient, datos: None, foto_png: bytes) -> None:
    reclamo = crear_reclamo(
        client, tipo="mal_estado", foto=("foto.png", foto_png, "image/png")
    ).json()
    url = reclamo["foto_url"]

    propia = client.get(url, headers=CLIENTE1)
    assert propia.status_code == 200
    assert propia.headers["content-type"] == "image/png"
    assert propia.content == foto_png

    assert client.get(url, headers=CLIENTE2).status_code == 404
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("nombre", ["..%2F..%2F.env", "inexistente.png", "a" * 32 + ".png"])
def test_foto_con_nombre_invalido_o_inexistente(
    client: TestClient, datos: None, nombre: str
) -> None:
    assert client.get(f"/api/v1/archivos/{nombre}", headers=CLIENTE1).status_code == 404
