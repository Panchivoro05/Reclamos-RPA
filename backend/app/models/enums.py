from enum import StrEnum


class CategoriaProducto(StrEnum):
    HAMBURGUESA = "hamburguesa"
    COMBO = "combo"
    ACOMPANAMIENTO = "acompañamiento"
    BEBIDA = "bebida"
    POSTRE = "postre"


class EstadoPedido(StrEnum):
    EN_PREPARACION = "en_preparacion"
    EN_CAMINO = "en_camino"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"


class TipoReclamo(StrEnum):
    PRODUCTO_EQUIVOCADO = "producto_equivocado"
    PEDIDO_INCOMPLETO = "pedido_incompleto"
    MAL_ESTADO = "mal_estado"
    DEMORA = "demora"


class EstadoReclamo(StrEnum):
    RECIBIDO = "recibido"
    EN_VALIDACION = "en_validacion"
    VALIDADO = "validado"
    EN_RESOLUCION = "en_resolucion"
    RESUELTO = "resuelto"
    CERRADO = "cerrado"
    ESCALADO = "escalado"


# Un reclamo "abierto" es cualquiera que todavía no termina su ciclo.
ESTADOS_RECLAMO_ABIERTO: frozenset[EstadoReclamo] = frozenset(
    set(EstadoReclamo) - {EstadoReclamo.RESUELTO, EstadoReclamo.CERRADO}
)


class ActorEvento(StrEnum):
    CLIENTE = "cliente"
    SISTEMA = "sistema"
    BOT = "bot"
    IA = "ia"
    AGENTE = "agente"
