from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# La sesión de PostgreSQL trabaja en UTC: la conversión a America/Lima se hace al mostrar.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"options": "-c timezone=UTC"},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    with SessionLocal() as session:
        yield session
