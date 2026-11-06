"""Sesión del operador y protección CSRF de los formularios."""

import secrets
from collections.abc import Callable
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from flask.typing import ResponseReturnValue

from caja.operadores import Operador, obtener_operador


def cargar_operador() -> None:
    """Antes de cada petición: deja en `g.operador` al operador con sesión (o None)."""
    operador_id = session.get("operador_id")
    g.operador = obtener_operador(operador_id) if isinstance(operador_id, int) else None
    if operador_id is not None and g.operador is None:
        # El operador ya no existe o fue desactivado.
        session.clear()


def login_requerido[**P](
    vista: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @wraps(vista)
    def envoltura(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        if g.get("operador") is None:
            return redirect(url_for("caja.login", siguiente=request.full_path.rstrip("?")))
        return vista(*args, **kwargs)

    return envoltura


def iniciar_sesion(operador: Operador) -> None:
    session.clear()  # evita fijación de sesión
    session["operador_id"] = operador.id


def token_csrf() -> str:
    """Token por sesión que cada formulario envía en un campo oculto."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def verificar_csrf() -> None:
    if request.method != "POST":
        return
    enviado = request.form.get("csrf_token", "")
    esperado = session.get("csrf", "")
    if not esperado or not secrets.compare_digest(enviado, esperado):
        abort(400, "La sesión del formulario expiró. Vuelva a intentarlo.")


def destino_seguro(siguiente: str | None) -> str:
    """Solo redirige a rutas internas (evita redirecciones abiertas)."""
    if siguiente and siguiente.startswith("/") and not siguiente.startswith("//"):
        return siguiente
    return url_for("caja.buscar_pedido")
