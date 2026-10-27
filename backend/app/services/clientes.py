from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import NoAutenticado
from app.core.security import IdentidadFirebase
from app.models import Cliente


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def obtener_por_email(session: Session, email: str) -> Cliente | None:
    return session.scalar(select(Cliente).where(Cliente.email == normalizar_email(email)))


def obtener_o_crear_desde_firebase(session: Session, identidad: IdentidadFirebase) -> Cliente:
    """Busca al cliente por su uid de Firebase; si no existe, lo vincula por correo o lo crea."""
    cliente = session.scalar(select(Cliente).where(Cliente.firebase_uid == identidad.uid))
    if cliente is not None:
        return cliente

    if not identidad.email:
        raise NoAutenticado(
            "cuenta_sin_correo", "Tu cuenta no tiene un correo asociado. Inicia sesión con correo."
        )

    # Un cliente que ya existía (por ejemplo, de la semilla) se vincula la primera vez.
    cliente = obtener_por_email(session, identidad.email)
    if cliente is None:
        email = normalizar_email(identidad.email)
        cliente = Cliente(email=email, nombre=identidad.nombre or email.split("@")[0])
        session.add(cliente)
    cliente.firebase_uid = identidad.uid
    session.commit()
    return cliente
