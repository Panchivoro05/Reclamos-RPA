"""Lo que el cliente ve de la resolución: resumen en el detalle y video del bot."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.services.almacenamiento import AlmacenamientoLocal
from app.services.bot import EjecutorBotSimulado, ResultadoBot
from app.services.procesamiento import procesar_reclamo
from tests.test_bot_proceso import salida_del_bot
from tests.test_procesamiento import nuevo_reclamo, un_combo
from tests.utils import CLIENTE1, CLIENTE2


def resolver_con_video(reclamo_id: int, carpeta_fotos: Path, tmp_path: Path) -> None:
    resultado = ResultadoBot(
        True, None, "ok", numero_operacion="CMP-000042", carpeta=salida_del_bot(tmp_path / "s")
    )
    with SessionLocal() as session:
        procesar_reclamo(
            session,
            reclamo_id,
            EjecutorBotSimulado([resultado]),
            almacenamiento=AlmacenamientoLocal(carpeta_fotos),
        )


def detalle(client: TestClient, codigo: str) -> dict[str, object]:
    respuesta = client.get(f"/api/v1/reclamos/{codigo}", headers=CLIENTE1)
    assert respuesta.status_code == 200
    datos: dict[str, object] = respuesta.json()
    return datos


def codigo_de(client: TestClient) -> str:
    return str(client.get("/api/v1/reclamos", headers=CLIENTE1).json()[0]["codigo"])


def test_recien_creado_no_tiene_resolucion(client: TestClient, datos: None) -> None:
    nuevo_reclamo(client, items=un_combo(client))
    assert detalle(client, codigo_de(client))["resolucion"] is None


def test_resuelto_muestra_la_compensacion_y_el_video(
    client: TestClient, datos: None, carpeta_fotos: Path, tmp_path: Path
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    resolver_con_video(reclamo_id, carpeta_fotos, tmp_path)
    codigo = codigo_de(client)

    assert detalle(client, codigo)["resolucion"] == {
        "solucion": "reembolso_parcial",
        "monto": "27.90",
        "descripcion": "un reembolso de S/ 27.90",
        "numero_operacion": "CMP-000042",
        "video_url": f"/api/v1/reclamos/{codigo}/video",
    }

    video = client.get(f"/api/v1/reclamos/{codigo}/video", headers=CLIENTE1)
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/webm"
    assert video.content == b"webm"


def test_el_video_solo_lo_ve_el_duenio(
    client: TestClient, datos: None, carpeta_fotos: Path, tmp_path: Path
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    resolver_con_video(reclamo_id, carpeta_fotos, tmp_path)
    codigo = codigo_de(client)

    assert client.get(f"/api/v1/reclamos/{codigo}/video", headers=CLIENTE2).status_code == 404
    assert client.get(f"/api/v1/reclamos/{codigo}/video").status_code == 401


def test_sin_video_todavia(client: TestClient, datos: None) -> None:
    nuevo_reclamo(client, items=un_combo(client))
    respuesta = client.get(f"/api/v1/reclamos/{codigo_de(client)}/video", headers=CLIENTE1)
    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "video_no_disponible"


def test_escalado_no_muestra_resolucion_ni_el_motivo_interno(
    client: TestClient, datos: None
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client, cantidad=2))  # S/ 55.80 > S/ 40
    with SessionLocal() as session:
        procesar_reclamo(session, reclamo_id, EjecutorBotSimulado())

    respuesta = client.get(f"/api/v1/reclamos/{codigo_de(client)}", headers=CLIENTE1)
    assert respuesta.json()["estado"] == "escalado"
    assert respuesta.json()["resolucion"] is None
    assert "monto máximo" not in respuesta.text
    assert "motivo_escalamiento" not in respuesta.text
