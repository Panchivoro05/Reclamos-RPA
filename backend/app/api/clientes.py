from fastapi import APIRouter

from app.api.deps import ClienteActual
from app.schemas.cliente import ClienteOut

router = APIRouter(tags=["clientes"])


@router.get("/me")
def me(cliente: ClienteActual) -> ClienteOut:
    return ClienteOut.model_validate(cliente)
