from fastapi import APIRouter, Response, status

from app.api.deps import ClienteActual, DbSession
from app.schemas.dispositivo import DispositivoEntrada
from app.services import dispositivos

router = APIRouter(prefix="/dispositivos", tags=["notificaciones"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
def registrar_dispositivo(
    db: DbSession, cliente: ClienteActual, entrada: DispositivoEntrada
) -> Response:
    """La app lo llama al iniciar sesión con el token de Expo Push del celular."""
    dispositivos.registrar(db, cliente, entrada.token, entrada.plataforma)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{token}", status_code=status.HTTP_204_NO_CONTENT)
def dar_de_baja_dispositivo(db: DbSession, cliente: ClienteActual, token: str) -> Response:
    """La app lo llama al cerrar sesión. Si el token no existe, igual responde 204."""
    dispositivos.dar_de_baja(db, cliente, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
