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


class SolucionCompensacion(StrEnum):
    """Lo que se registra en SISCAJA para resolver el reclamo (mismos valores que el bot)."""

    REENVIO = "reenvio"
    REEMBOLSO_PARCIAL = "reembolso_parcial"
    REEMBOLSO_TOTAL = "reembolso_total"
    CUPON = "cupon"


class BaseMonto(StrEnum):
    """Cómo se calcula el monto de la compensación a partir de la regla."""

    NINGUNO = "ninguno"  # reenvío: no hay dinero de por medio
    ITEMS_AFECTADOS = "items_afectados"  # suma de cantidad afectada x precio unitario
    FIJO = "fijo"  # el valor de la regla, en soles
    PORCENTAJE_TOTAL = "porcentaje_total"  # el valor de la regla, como % del total del pedido
    TOTAL_PEDIDO = "total_pedido"  # el total del pedido


class PlataformaDispositivo(StrEnum):
    ANDROID = "android"
    IOS = "ios"


class CanalNotificacion(StrEnum):
    PUSH = "push"
    CORREO = "correo"


class EstadoNotificacion(StrEnum):
    ENVIANDO = "enviando"  # se reservó el envío (evita duplicados si la tarea se repite)
    ENVIADA = "enviada"
    FALLIDA = "fallida"
    OMITIDA = "omitida"  # no había a quién enviarla (sin dispositivos, sin correo...)


class OperacionIA(StrEnum):
    CLASIFICAR_TEXTO = "clasificar_texto"
    ANALIZAR_FOTO = "analizar_foto"
    REDACTAR_MENSAJE = "redactar_mensaje"
    ASISTENTE = "asistente"
