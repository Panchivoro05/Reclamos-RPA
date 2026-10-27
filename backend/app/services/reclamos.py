"""Registro y consulta de reclamos con sus reglas de negocio."""

import json
from collections.abc import Sequence
from datetime import datetime, timedelta

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errores import ArchivoMuyGrande, Conflicto, DatosInvalidos, NoEncontrado, ReglaNegocio
from app.core.tiempo import ZONA_LIMA, ahora_utc, formato_lima
from app.models import (
    ActorEvento,
    Cliente,
    EstadoPedido,
    EstadoReclamo,
    Pedido,
    Reclamo,
    ReclamoEvento,
    ReclamoItem,
    TipoReclamo,
    reclamo_codigo_seq,
)
from app.models.enums import ESTADOS_RECLAMO_ABIERTO
from app.schemas.reclamo import ReclamoItemEntrada
from app.services.almacenamiento import PATRON_NOMBRE, AlmacenamientoArchivos
from app.services.pedidos import obtener_pedido

TIPOS_CON_FOTO_OBLIGATORIA = frozenset({TipoReclamo.PRODUCTO_EQUIVOCADO, TipoReclamo.MAL_ESTADO})
TIPOS_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

MENSAJE_RECIBIDO = "Recibimos tu reclamo. Lo estamos revisando y te avisaremos por aquí."

_items_adapter = TypeAdapter(list[ReclamoItemEntrada])


# ---------- Entrada ----------


def parsear_items(texto: str) -> list[ReclamoItemEntrada]:
    """Convierte el campo de formulario `items` (texto JSON) en la lista de ítems afectados."""
    if not texto.strip():
        return []
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as error:
        raise DatosInvalidos(
            "items_invalidos", "La lista de productos afectados no tiene un formato válido."
        ) from error
    try:
        return _items_adapter.validate_python(datos)
    except ValidationError as error:
        raise ReglaNegocio(
            "items_invalidos",
            "Cada producto afectado debe indicar el ítem del pedido y una cantidad mayor que cero.",
        ) from error


def detectar_formato_imagen(contenido: bytes) -> str | None:
    """Extensión según los primeros bytes del archivo (no se confía en el nombre ni en el
    Content-Type que envía el cliente)."""
    if contenido.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "webp"
    return None


# ---------- Reglas ----------


def _validar_pedido_reclamable(pedido: Pedido, tipo: TipoReclamo, ahora: datetime) -> None:
    if pedido.estado is EstadoPedido.CANCELADO:
        raise ReglaNegocio(
            "pedido_no_reclamable", "Este pedido fue cancelado, así que no admite reclamos."
        )
    if pedido.estado is EstadoPedido.EN_PREPARACION:
        raise ReglaNegocio(
            "pedido_no_reclamable",
            "Tu pedido todavía se está preparando. "
            "Podrás reportar una demora cuando esté en camino.",
        )
    if pedido.estado is EstadoPedido.EN_CAMINO:
        if tipo is not TipoReclamo.DEMORA:
            raise ReglaNegocio(
                "pedido_no_reclamable",
                "Tu pedido aún está en camino. Por ahora solo puedes reportar una demora; "
                "los demás reclamos se habilitan cuando lo recibas.",
            )
        return

    # Entregado: se acepta dentro del plazo desde la entrega.
    plazo_horas = get_settings().reclamo_plazo_horas
    entregado_en = pedido.entregado_en or pedido.creado_en
    limite = entregado_en + timedelta(hours=plazo_horas)
    if ahora > limite:
        raise ReglaNegocio(
            "fuera_de_plazo",
            f"El plazo para reclamar este pedido venció el {formato_lima(limite)}. "
            f"Los reclamos se aceptan hasta {plazo_horas} horas después de la entrega.",
        )


def _validar_items(pedido: Pedido, tipo: TipoReclamo, items: list[ReclamoItemEntrada]) -> None:
    if not items and tipo is not TipoReclamo.DEMORA:
        raise ReglaNegocio(
            "items_requeridos", "Indica qué productos del pedido tuvieron el problema."
        )

    items_pedido = {item.id: item for item in pedido.items}
    vistos: set[int] = set()
    for entrada in items:
        item_pedido = items_pedido.get(entrada.pedido_item_id)
        if item_pedido is None:
            raise ReglaNegocio(
                "item_no_pertenece", "Uno de los productos indicados no pertenece a este pedido."
            )
        if entrada.pedido_item_id in vistos:
            raise ReglaNegocio(
                "item_repetido", f"El producto {item_pedido.producto.nombre} está repetido."
            )
        vistos.add(entrada.pedido_item_id)
        if entrada.cantidad_afectada > item_pedido.cantidad:
            raise ReglaNegocio(
                "cantidad_excedida",
                f"Pediste {item_pedido.cantidad} de {item_pedido.producto.nombre}; "
                f"no puedes reclamar {entrada.cantidad_afectada}.",
            )


def _validar_foto(tipo: TipoReclamo, foto: bytes | None) -> str | None:
    """Valida la foto y devuelve su extensión (None si no se envió)."""
    if not foto:
        if tipo in TIPOS_CON_FOTO_OBLIGATORIA:
            raise ReglaNegocio(
                "foto_requerida", "Para este tipo de reclamo necesitamos una foto del producto."
            )
        return None

    maximo = get_settings().foto_max_bytes
    if len(foto) > maximo:
        raise ArchivoMuyGrande(
            "foto_muy_grande", f"La foto pesa demasiado. El máximo es {maximo // (1024 * 1024)} MB."
        )
    extension = detectar_formato_imagen(foto)
    if extension is None:
        raise DatosInvalidos(
            "foto_formato_invalido", "La foto debe ser una imagen JPG, PNG o WEBP."
        )
    return extension


def _tipos_abiertos(session: Session, pedido: Pedido) -> set[TipoReclamo]:
    return set(
        session.scalars(
            select(Reclamo.tipo).where(
                Reclamo.pedido_id == pedido.id, Reclamo.estado.in_(ESTADOS_RECLAMO_ABIERTO)
            )
        )
    )


def tipos_disponibles(
    session: Session, pedido: Pedido, ahora: datetime | None = None
) -> list[TipoReclamo]:
    """Tipos de reclamo que el cliente puede registrar ahora para este pedido.

    La app lo usa para mostrar u ocultar el botón "Tengo un problema con mi pedido".
    """
    ahora = ahora or ahora_utc()
    abiertos = _tipos_abiertos(session, pedido)
    disponibles: list[TipoReclamo] = []
    for tipo in TipoReclamo:
        if tipo in abiertos:
            continue
        try:
            _validar_pedido_reclamable(pedido, tipo, ahora)
        except ReglaNegocio:
            continue
        disponibles.append(tipo)
    return disponibles


# ---------- Casos de uso ----------


def _generar_codigo(session: Session, ahora: datetime) -> str:
    numero = session.execute(select(reclamo_codigo_seq.next_value())).scalar_one()
    return f"RC-{ahora.astimezone(ZONA_LIMA).year}-{numero:06d}"


def crear_reclamo(
    session: Session,
    almacenamiento: AlmacenamientoArchivos,
    cliente: Cliente,
    *,
    pedido_codigo: str,
    tipo: TipoReclamo,
    descripcion: str,
    items: list[ReclamoItemEntrada],
    foto: bytes | None,
    ahora: datetime | None = None,
) -> Reclamo:
    ahora = ahora or ahora_utc()

    pedido = obtener_pedido(session, cliente, pedido_codigo)
    _validar_pedido_reclamable(pedido, tipo, ahora)
    _validar_items(pedido, tipo, items)
    extension = _validar_foto(tipo, foto)
    if tipo in _tipos_abiertos(session, pedido):
        raise _reclamo_duplicado()

    # La foto se guarda al final, cuando ya pasaron todas las validaciones.
    foto_ruta = almacenamiento.guardar(foto, extension) if foto and extension else None

    reclamo = Reclamo(
        codigo=_generar_codigo(session, ahora),
        pedido=pedido,
        cliente_id=cliente.id,
        tipo=tipo,
        estado=EstadoReclamo.RECIBIDO,
        descripcion=descripcion.strip(),
        foto_ruta=foto_ruta,
        items=[
            ReclamoItem(pedido_item_id=i.pedido_item_id, cantidad_afectada=i.cantidad_afectada)
            for i in items
        ],
        eventos=[
            ReclamoEvento(
                estado=EstadoReclamo.RECIBIDO, mensaje=MENSAJE_RECIBIDO, actor=ActorEvento.CLIENTE
            )
        ],
    )
    session.add(reclamo)
    try:
        session.commit()
    except Exception as error:
        session.rollback()
        if foto_ruta:
            almacenamiento.eliminar(foto_ruta)
        if isinstance(error, IntegrityError):
            # Otra petición simultánea registró el mismo reclamo (índice único parcial).
            raise _reclamo_duplicado() from error
        raise

    return obtener_reclamo(session, cliente, reclamo.codigo)


def _reclamo_duplicado() -> Conflicto:
    return Conflicto(
        "reclamo_duplicado",
        "Ya tienes un reclamo abierto de este tipo para este pedido. "
        "Puedes ver su avance en Mis reclamos.",
    )


def listar_reclamos(session: Session, cliente: Cliente) -> Sequence[Reclamo]:
    return session.scalars(
        select(Reclamo)
        .where(Reclamo.cliente_id == cliente.id)
        .options(selectinload(Reclamo.pedido))
        .order_by(Reclamo.creado_en.desc(), Reclamo.id.desc())
    ).all()


def obtener_reclamo(session: Session, cliente: Cliente, codigo: str) -> Reclamo:
    codigo = codigo.strip().upper()
    reclamo = session.scalar(
        select(Reclamo)
        .where(Reclamo.codigo == codigo, Reclamo.cliente_id == cliente.id)
        .options(
            selectinload(Reclamo.pedido),
            selectinload(Reclamo.items),
            selectinload(Reclamo.eventos),
        )
        .execution_options(populate_existing=True)
    )
    if reclamo is None:
        raise NoEncontrado(
            "reclamo_no_encontrado", f"No encontramos el reclamo {codigo} en tu cuenta."
        )
    return reclamo


def obtener_foto(
    session: Session, almacenamiento: AlmacenamientoArchivos, cliente: Cliente, nombre: str
) -> tuple[bytes, str]:
    """Contenido y tipo MIME de una foto, solo si pertenece a un reclamo del cliente."""
    no_encontrada = NoEncontrado("archivo_no_encontrado", "No encontramos esa foto.")
    if not PATRON_NOMBRE.match(nombre):
        raise no_encontrada
    es_del_cliente = session.scalar(
        select(Reclamo.id).where(Reclamo.foto_ruta == nombre, Reclamo.cliente_id == cliente.id)
    )
    contenido = almacenamiento.leer(nombre) if es_del_cliente else None
    if contenido is None:
        raise no_encontrada
    extension = nombre.rsplit(".", 1)[1]
    return contenido, TIPOS_MIME[extension]
