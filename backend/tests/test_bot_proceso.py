"""Ejecutor real del bot (con un "bot" falso de línea de comandos) y guardado de evidencia."""

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import EjecucionBot, SolucionCompensacion
from app.services.almacenamiento import AlmacenamientoLocal
from app.services.bot import EjecutorBotSimulado, ResultadoBot, SolicitudBot
from app.services.bot_proceso import EjecutorBotProceso, resultado_desde_json
from app.services.evidencia import guardar_evidencia
from app.services.procesamiento import Resultado, procesar_reclamo
from tests.test_procesamiento import nuevo_reclamo, un_combo

SOLICITUD = SolicitudBot(
    reclamo_codigo="RC-2026-000001",
    pedido_codigo="BY-000101",
    solucion=SolucionCompensacion.REEMBOLSO_PARCIAL,
    monto=Decimal("27.9"),
    motivo="RC-2026-000001 - Pedido incompleto: faltó un combo",
    items_esperados=[{"producto": "Combo Clásico", "cantidad": 1}],
    total_esperado=Decimal("82.5"),
)


def bot_falso(carpeta: Path, cuerpo: str) -> EjecutorBotProceso:
    """Un "bot_rpa" de mentira: un paquete con __main__.py que hace lo que diga `cuerpo`."""
    paquete = carpeta / "bot_rpa"
    paquete.mkdir(parents=True)
    (paquete / "__init__.py").write_text("")
    (paquete / "__main__.py").write_text(cuerpo)
    return EjecutorBotProceso(Path(sys.executable), carpeta, timeout_s=5)


def test_comando_incluye_lo_que_el_bot_debe_verificar(tmp_path: Path) -> None:
    comando = EjecutorBotProceso(Path("/py"), tmp_path, 10).comando(SOLICITUD)
    assert comando[:3] == ["/py", "-m", "bot_rpa"]
    argumentos = dict(zip(comando[3::2], comando[4::2], strict=True))
    assert argumentos == {
        "--pedido": "BY-000101",
        "--solucion": "reembolso_parcial",
        "--motivo": "RC-2026-000001 - Pedido incompleto: faltó un combo",
        "--reclamo": "RC-2026-000001",
        "--monto": "27.90",
        "--items-esperados": '[{"producto": "Combo Clásico", "cantidad": 1}]',
        "--total-esperado": "82.50",
    }


def test_reenvio_no_envia_monto(tmp_path: Path) -> None:
    reenvio = SolicitudBot(
        reclamo_codigo="RC-2026-000001",
        pedido_codigo="BY-000101",
        solucion=SolucionCompensacion.REENVIO,
        monto=Decimal("0"),
        motivo="x",
    )
    assert "--monto" not in EjecutorBotProceso(Path("/py"), tmp_path, 10).comando(reenvio)


def test_lee_el_json_del_bot(tmp_path: Path) -> None:
    salida = {
        "exito": True,
        "codigo_error": None,
        "mensaje": "Compensacion registrada en SISCAJA.",
        "carpeta": str(tmp_path / "salida"),
        "numero_operacion": "CMP-000009",
        "pasos": [{"paso": "login", "captura": "capturas/01_login.png"}],
        "video": "video.webm",
        "duracion_s": 7.2,
    }
    ejecutor = bot_falso(tmp_path / "bot", f"import json; print(json.dumps({salida!r}))")

    resultado = ejecutor.resolver(SOLICITUD)

    assert resultado.exito
    assert resultado.numero_operacion == "CMP-000009"
    assert resultado.carpeta == tmp_path / "salida"
    assert resultado.pasos[0]["paso"] == "login"


def test_bot_colgado_es_tiempo_agotado(tmp_path: Path) -> None:
    ejecutor = bot_falso(tmp_path / "bot", "import time; time.sleep(30)")
    ejecutor.timeout_s = 1
    resultado = ejecutor.resolver(SOLICITUD)
    assert (resultado.exito, resultado.codigo_error) == (False, "tiempo_agotado")
    assert resultado.es_error_tecnico


def test_salida_que_no_es_json(tmp_path: Path) -> None:
    ejecutor = bot_falso(
        tmp_path / "bot", "import sys; print('Traceback: algo exploto', file=sys.stderr)"
    )
    resultado = ejecutor.resolver(SOLICITUD)
    assert resultado.codigo_error == "error_inesperado"
    assert "algo exploto" in resultado.mensaje


def test_bot_no_instalado(tmp_path: Path) -> None:
    resultado = EjecutorBotProceso(tmp_path / "no-existe" / "python", tmp_path, 5).resolver(
        SOLICITUD
    )
    assert resultado.codigo_error == "error_inesperado"
    assert "No se encontró el bot" in resultado.mensaje


def test_error_de_negocio_del_bot_no_es_tecnico() -> None:
    resultado = resultado_desde_json(
        {"exito": False, "codigo_error": "compensacion_rechazada", "mensaje": "Monto excedido"}
    )
    assert not resultado.es_error_tecnico


# ---------- Evidencia ----------


def salida_del_bot(carpeta: Path) -> Path:
    """Carpeta como la que deja el bot: resultado.json, video y capturas."""
    (carpeta / "capturas").mkdir(parents=True)
    (carpeta / "resultado.json").write_text(json.dumps({"exito": True}))
    (carpeta / "video.webm").write_bytes(b"webm")
    (carpeta / "capturas" / "01_login.png").write_bytes(b"png1")
    (carpeta / "capturas" / "05_comprobante.png").write_bytes(b"png5")
    (carpeta / "capturas" / "nota.txt").write_text("no se copia")
    (carpeta / "robot").mkdir()
    (carpeta / "robot" / "log.html").write_text("no se copia")
    return carpeta


def test_guarda_capturas_video_y_resultado(tmp_path: Path) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path / "uploads")
    resultado = ResultadoBot(True, None, "ok", carpeta=salida_del_bot(tmp_path / "salida"))

    evidencia = guardar_evidencia(almacenamiento, resultado, "RC-2026-000007", intento=2)

    assert evidencia is not None
    assert evidencia.carpeta == "evidencias/RC-2026-000007/intento-2"
    assert evidencia.video == "evidencias/RC-2026-000007/intento-2/video.webm"
    base = tmp_path / "uploads" / "evidencias" / "RC-2026-000007" / "intento-2"
    copiados = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
    assert copiados == [
        "capturas/01_login.png",
        "capturas/05_comprobante.png",
        "resultado.json",
        "video.webm",
    ]
    assert almacenamiento.leer_evidencia(f"{evidencia.carpeta}/capturas/01_login.png") == b"png1"


@pytest.mark.parametrize(
    "ruta",
    [
        "../../.env",
        "evidencias/RC-2026-000001/intento-1/../../../.env",
        "evidencias/RC-2026-000001/intento-1/robot/log.html",
        "evidencias/otra-cosa/intento-1/video.webm",
    ],
)
def test_rutas_de_evidencia_no_permitidas(tmp_path: Path, ruta: str) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    assert almacenamiento.leer_evidencia(ruta) is None
    with pytest.raises(ValueError):
        almacenamiento.guardar_evidencia(ruta, b"x")


def test_sin_carpeta_no_hay_evidencia(tmp_path: Path) -> None:
    resultado = ResultadoBot(False, "tiempo_agotado", "colgado")
    assert guardar_evidencia(AlmacenamientoLocal(tmp_path), resultado, "RC-2026-000001", 1) is None


def test_el_procesamiento_asocia_la_evidencia_al_reclamo(
    client: TestClient, datos: None, db: Session, tmp_path: Path
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    carpeta = salida_del_bot(tmp_path / "salida")
    bot = EjecutorBotSimulado(
        [ResultadoBot(True, None, "ok", numero_operacion="CMP-000001", carpeta=carpeta)]
    )
    almacenamiento = AlmacenamientoLocal(tmp_path / "uploads")

    with SessionLocal() as session:
        resultado = procesar_reclamo(session, reclamo_id, bot, almacenamiento=almacenamiento)

    assert resultado == Resultado.RESUELTO
    ejecucion = db.query(EjecucionBot).filter_by(reclamo_id=reclamo_id).one()
    assert ejecucion.evidencia is not None and ejecucion.evidencia.endswith("/intento-1")
    assert ejecucion.video == f"{ejecucion.evidencia}/video.webm"
    assert almacenamiento.leer_evidencia(ejecucion.video) == b"webm"
