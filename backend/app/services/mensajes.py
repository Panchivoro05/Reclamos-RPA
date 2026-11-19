"""Mensajes al cliente en los hitos del reclamo, redactados por la IA y verificados por el código.

La plantilla (con los datos correctos: monto, número de operación) es la fuente de verdad. La
IA solo la reescribe con un tono más cálido. Antes de usar su texto se verifica que:

- contenga cada dato obligatorio exacto (monto, número de operación);
- no tenga números que no estén en la plantilla (ni montos inventados ni plazos prometidos);
- no revele temas internos (fraude, IA, reglas) ni incluya enlaces o correos;
- tenga un largo razonable.

Si algo no cumple, o la IA falla o tarda, se usa la plantilla: el cliente nunca ve un dato
equivocado y el reclamo nunca se detiene por el mensaje.
"""

import logging
import re

from sqlalchemy.orm import Session

from app.models import EstadoReclamo, OperacionIA, Reclamo
from app.services.ia import (
    EntradaMensaje,
    ErrorIA,
    MensajeRedactado,
    ProveedorIA,
    RespuestaIA,
)
from app.services.ia_registro import llamar

logger = logging.getLogger(__name__)

# Hitos en los que la IA redacta; los estados intermedios usan siempre texto fijo.
HITOS_REDACTADOS = frozenset(
    {EstadoReclamo.VALIDADO, EstadoReclamo.RESUELTO, EstadoReclamo.ESCALADO}
)

LARGO_MINIMO = 20
LARGO_MAXIMO = 320

# Temas internos que el cliente no debe ver (sobre el texto en minúsculas).
PROHIBIDOS = re.compile(
    r"fraude|sospech|inteligencia artificial|\bia\b|algoritmo|umbral|\breglas?\b"
    r"|http|www\.|@"
)
NUMEROS = re.compile(r"\d+")


def motivo_de_rechazo(texto: str, plantilla: str, obligatorios: list[str]) -> str | None:
    """Por qué el texto de la IA no se puede usar (None si se puede)."""
    if not LARGO_MINIMO <= len(texto) <= LARGO_MAXIMO:
        return f"largo fuera de rango ({len(texto)} caracteres)"
    faltantes = [dato for dato in obligatorios if dato not in texto]
    if faltantes:
        return f"falta {', '.join(faltantes)}"
    permitidos = set(NUMEROS.findall(plantilla))
    inventados = sorted(set(NUMEROS.findall(texto)) - permitidos)
    if inventados:
        return f"números que no están en la plantilla: {', '.join(inventados)}"
    prohibido = PROHIBIDOS.search(texto.lower())
    if prohibido:
        return f"menciona un tema interno ({prohibido.group()!r})"
    return None


def redactar(
    session: Session,
    reclamo: Reclamo,
    estado: EstadoReclamo,
    plantilla: str,
    obligatorios: list[str],
    ia: ProveedorIA | None,
) -> str:
    """Mensaje para el cliente: el de la IA si pasa la verificación; si no, la plantilla."""
    if ia is None or estado not in HITOS_REDACTADOS:
        return plantilla
    entrada = EntradaMensaje(
        estado=estado,
        tipo=reclamo.tipo,
        productos_reclamados=[item.pedido_item.producto.nombre for item in reclamo.items],
        mensaje_base=plantilla,
    )

    def redactar_y_verificar() -> RespuestaIA[MensajeRedactado]:
        respuesta = ia.redactar_mensaje(entrada)
        texto = respuesta.resultado.mensaje = respuesta.resultado.mensaje.strip()
        motivo = motivo_de_rechazo(texto, plantilla, obligatorios)
        if motivo:
            # Como error: queda registrado (exito=False) y se usa la plantilla.
            raise ErrorIA(f"Mensaje rechazado: {motivo}. Texto: {texto}")
        return respuesta

    try:
        redactado = llamar(
            session,
            OperacionIA.REDACTAR_MENSAJE,
            ia.nombre,
            redactar_y_verificar,
            reclamo_id=reclamo.id,
        )
    except ErrorIA:
        logger.info("Reclamo %s: se usa la plantilla del mensaje (%s)", reclamo.codigo, estado)
        return plantilla
    return redactado.mensaje
