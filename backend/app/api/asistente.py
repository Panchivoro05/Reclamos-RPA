from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import ClienteActual, DbSession
from app.schemas.asistente import ConsultaAsistente, RespuestaAsistenteOut
from app.services import asistente
from app.services.ia import MensajeChat, ProveedorIA, get_proveedor_ia
from app.services.limites import controlar_consultas_asistente

router = APIRouter(tags=["asistente"])


@router.post("/asistente")
def consultar_asistente(
    db: DbSession,
    cliente: ClienteActual,
    ia: Annotated[ProveedorIA, Depends(get_proveedor_ia)],
    consulta: ConsultaAsistente,
) -> RespuestaAsistenteOut:
    """Responde sobre los pedidos y reclamos del cliente (solo informa, no cambia nada)."""
    controlar_consultas_asistente(cliente.id)
    mensajes = [MensajeChat(m.rol, m.texto) for m in consulta.mensajes]
    return RespuestaAsistenteOut(respuesta=asistente.responder(db, cliente, mensajes, ia))
