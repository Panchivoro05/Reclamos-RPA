"""Tokens de Expo Push de los celulares del cliente."""

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Cliente, Dispositivo, PlataformaDispositivo


def registrar(
    session: Session, cliente: Cliente, token: str, plataforma: PlataformaDispositivo
) -> Dispositivo:
    """Guarda (o reactiva) el token. Si ese celular era de otro cliente, ahora es de este:
    un token identifica al celular, y en un celular hay una sola sesión a la vez."""
    dispositivo = session.scalar(select(Dispositivo).where(Dispositivo.token == token))
    if dispositivo is None:
        dispositivo = Dispositivo(token=token)
        session.add(dispositivo)
    dispositivo.cliente_id = cliente.id
    dispositivo.plataforma = plataforma
    dispositivo.activo = True
    session.commit()
    return dispositivo


def dar_de_baja(session: Session, cliente: Cliente, token: str) -> None:
    """Al cerrar sesión el celular deja de recibir avisos de ese cliente."""
    session.execute(
        update(Dispositivo)
        .where(Dispositivo.token == token, Dispositivo.cliente_id == cliente.id)
        .values(activo=False)
    )
    session.commit()


def desactivar_tokens(session: Session, tokens: Sequence[str]) -> None:
    """Expo avisó que la app ya no está en esos celulares (DeviceNotRegistered)."""
    if tokens:
        session.execute(
            update(Dispositivo).where(Dispositivo.token.in_(tokens)).values(activo=False)
        )
        session.commit()


def activos(session: Session, cliente_id: int) -> Sequence[Dispositivo]:
    return session.scalars(
        select(Dispositivo)
        .where(Dispositivo.cliente_id == cliente_id, Dispositivo.activo.is_(True))
        .order_by(Dispositivo.id)
    ).all()
