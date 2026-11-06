"""Levanta un SISCAJA de prueba (SQLite temporal, puerto libre) para ejecutar el bot de verdad.

El bot se prueba de punta a punta: navegador real, robot real y SISCAJA real; solo cambian los
datos. SISCAJA corre con el Python de su propio entorno (sistema-caja/.venv) o, si `caja` está
instalado en el entorno actual (como en CI), con este mismo Python.
"""

import importlib.util
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from bot_rpa.config import Settings

RAIZ_REPO = Path(__file__).resolve().parents[2]
USUARIO = "bot_prueba"
CLAVE = "clave-del-bot-de-prueba"

# Pedidos de prueba (montos en céntimos). BY-000301: 2 x 18.90 + 1 x 8.50 = 46.30.
PEDIDOS = [
    ("BY-000301", "entregado", 4630, [("Hamburguesa Clásica", 2, 1890), ("Papas Fritas", 1, 850)]),
    ("BY-000302", "cancelado", 2500, [("Combo Doble", 1, 2500)]),
]


def python_de_siscaja() -> str:
    if importlib.util.find_spec("caja") is not None:
        return sys.executable
    propio = RAIZ_REPO / "sistema-caja" / ".venv" / "bin" / "python"
    if propio.exists():
        return str(propio)
    pytest.exit(
        "No se encontró SISCAJA: crea sistema-caja/.venv (ver README) o instala sistema-caja "
        "en este entorno con: pip install -e ../sistema-caja",
        returncode=2,
    )


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def esperar_servidor(url: str, proceso: subprocess.Popen[bytes], segundos: float = 15) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            raise RuntimeError("SISCAJA terminó al arrancar")
        try:
            urllib.request.urlopen(f"{url}/login", timeout=1)
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"SISCAJA no respondió en {url}")


def insertar_pedidos(ruta_db: Path) -> None:
    conexion = sqlite3.connect(ruta_db)
    for codigo, estado, total, items in PEDIDOS:
        cursor = conexion.execute(
            """
            INSERT INTO pedidos (codigo, cliente_nombre, cliente_email, estado, total_centimos,
                local, direccion_entrega, creado_en, entregado_en, sincronizado_en)
            VALUES (?, 'María Quispe', 'cliente1@burgerya.pe', ?, ?, 'BurgerYa Miraflores',
                'Av. Larco 123', '2026-10-27T17:00:00+00:00', '2026-10-27T17:45:00+00:00',
                '2026-10-27T18:00:00+00:00')
            """,
            (codigo, estado, total),
        )
        conexion.executemany(
            "INSERT INTO pedido_items (pedido_id, producto, cantidad, precio_unitario_centimos) "
            "VALUES (?, ?, ?, ?)",
            [(cursor.lastrowid, *item) for item in items],
        )
    conexion.commit()
    conexion.close()


@pytest.fixture(scope="session")
def siscaja(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    """SISCAJA corriendo en un puerto libre. Devuelve (url, ruta de su SQLite)."""
    carpeta = tmp_path_factory.mktemp("siscaja")
    ruta_db = carpeta / "caja.db"
    entorno = {
        **os.environ,
        "CAJA_DB_PATH": str(ruta_db),
        "CAJA_SECRET_KEY": "pruebas-del-bot",
        "CAJA_OPERADOR_USUARIO": USUARIO,
        "CAJA_OPERADOR_NOMBRE": "Bot de Prueba",
        "CAJA_OPERADOR_CLAVE": CLAVE,
    }
    python = python_de_siscaja()
    flask = [python, "-m", "flask", "--app", "caja"]
    # cwd = carpeta temporal: así SISCAJA no lee el .env del repositorio.
    subprocess.run([*flask, "init-db"], cwd=carpeta, env=entorno, check=True, capture_output=True)
    insertar_pedidos(ruta_db)

    puerto = puerto_libre()
    url = f"http://127.0.0.1:{puerto}"
    proceso = subprocess.Popen(
        [*flask, "run", "--host", "127.0.0.1", "--port", str(puerto)],
        cwd=carpeta,
        env=entorno,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        esperar_servidor(url, proceso)
        yield url, ruta_db
    finally:
        proceso.terminate()
        proceso.wait(timeout=10)


@pytest.fixture
def caja_db(siscaja: tuple[str, Path]) -> Iterator[sqlite3.Connection]:
    """Conexión a la base de SISCAJA; cada prueba empieza sin compensaciones."""
    conexion = sqlite3.connect(siscaja[1])
    conexion.row_factory = sqlite3.Row
    conexion.execute("DELETE FROM compensaciones")
    conexion.commit()
    yield conexion
    conexion.close()


@pytest.fixture
def ajustes(siscaja: tuple[str, Path], tmp_path: Path) -> Settings:
    """Configuración del bot apuntando al SISCAJA de prueba, en modo oculto."""
    return Settings(
        caja_url=siscaja[0],
        operador_usuario=USUARIO,
        operador_clave=CLAVE,
        salidas_dir=tmp_path / "salidas",
        visible=False,
        grabar_video=False,
        timeout_s=120,
    )
