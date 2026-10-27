from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from app.api.deps import Almacenamiento, ClienteActual, DbSession, SettingsDep
from app.models import TipoReclamo
from app.schemas.reclamo import ReclamoDetalle, ReclamoResumen
from app.services import reclamos
from app.services.cola import encolar_reclamo

router = APIRouter(tags=["reclamos"])


@router.post("/reclamos", status_code=status.HTTP_201_CREATED)
def crear_reclamo(
    db: DbSession,
    cliente: ClienteActual,
    almacenamiento: Almacenamiento,
    settings: SettingsDep,
    pedido_codigo: Annotated[str, Form(min_length=1, max_length=20)],
    tipo: Annotated[TipoReclamo, Form()],
    descripcion: Annotated[str, Form(min_length=10, max_length=1000)],
    items: Annotated[
        str, Form(description='Lista JSON: [{"pedido_item_id": 1, "cantidad_afectada": 1}]')
    ] = "[]",
    foto: Annotated[UploadFile | None, File(description="JPG, PNG o WEBP")] = None,
) -> ReclamoDetalle:
    # Se lee un byte más del máximo para detectar archivos demasiado grandes sin cargarlos enteros.
    contenido_foto = foto.file.read(settings.foto_max_bytes + 1) if foto else None
    reclamo = reclamos.crear_reclamo(
        db,
        almacenamiento,
        cliente,
        pedido_codigo=pedido_codigo,
        tipo=tipo,
        descripcion=descripcion,
        items=reclamos.parsear_items(items),
        foto=contenido_foto,
    )
    encolar_reclamo(reclamo)
    return ReclamoDetalle.desde_reclamo(reclamo)


@router.get("/reclamos")
def listar_reclamos(db: DbSession, cliente: ClienteActual) -> list[ReclamoResumen]:
    return [ReclamoResumen.desde(r) for r in reclamos.listar_reclamos(db, cliente)]


@router.get("/reclamos/{codigo}")
def obtener_reclamo(db: DbSession, cliente: ClienteActual, codigo: str) -> ReclamoDetalle:
    return ReclamoDetalle.desde_reclamo(reclamos.obtener_reclamo(db, cliente, codigo))


@router.get(
    "/archivos/{nombre}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}}},
)
def obtener_archivo(
    db: DbSession, cliente: ClienteActual, almacenamiento: Almacenamiento, nombre: str
) -> Response:
    """Foto de un reclamo; solo la ve el dueño del reclamo."""
    contenido, tipo_mime = reclamos.obtener_foto(db, almacenamiento, cliente, nombre)
    return Response(
        content=contenido, media_type=tipo_mime, headers={"Cache-Control": "private, max-age=3600"}
    )
