"""Configuración común de las pruebas.

Las pruebas usan una base de datos propia (por defecto <base>_test en el mismo servidor
de DATABASE_URL, o TEST_DATABASE_URL si se define). Se crea desde cero con las
migraciones de Alembic al iniciar la sesión de pytest, y las tablas se vacían después
de cada prueba. La base de desarrollo nunca se toca.
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import make_url

from app.core.config import Settings, get_settings

# Debe ejecutarse antes de importar app.core.db: el engine se crea al importarlo.
_url_base = make_url(Settings().database_url)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _url_base.set(
    database=f"{_url_base.database}_test"
).render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["AUTH_MODE"] = "dev"
get_settings.cache_clear()

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services.almacenamiento import AlmacenamientoLocal, get_almacenamiento  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _recrear_base_de_datos(url: str) -> None:
    destino = make_url(url)
    # Conexión de administración a la base "postgres" del mismo servidor.
    admin = destino.set(drivername="postgresql", database="postgres")
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{destino.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{destino.database}"')


@pytest.fixture(scope="session", autouse=True)
def base_de_datos() -> Iterator[None]:
    _recrear_base_de_datos(TEST_DATABASE_URL)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _vaciar_tablas() -> Iterator[None]:
    yield
    tablas = ", ".join(tabla.name for tabla in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER SEQUENCE reclamo_codigo_seq RESTART"))


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def datos(db: Session) -> None:
    """Carga la semilla de BurgerYa (fechas relativas a la hora actual)."""
    seed(db)


@pytest.fixture
def carpeta_fotos(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


@pytest.fixture
def client(carpeta_fotos: Path) -> Iterator[TestClient]:
    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoLocal(carpeta_fotos)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def configurar(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Cambia la configuración solo durante la prueba: configurar(reclamo_plazo_horas=100)."""

    def _configurar(**valores: object) -> None:
        for nombre, valor in valores.items():
            monkeypatch.setenv(nombre.upper(), str(valor))
        get_settings.cache_clear()

    yield _configurar
    get_settings.cache_clear()


@pytest.fixture
def foto_png() -> bytes:
    """PNG válido de 1x1 píxel."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00"
        b"\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81"
        b"\x84\x00\x00\x00\x00IEND\xaeB`\x82"
    )
