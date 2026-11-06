"""Pantallas de SISCAJA. Solo HTML y formularios: este sistema no tiene API."""

from flask import Blueprint, abort, g, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from caja import pedidos
from caja.operadores import autenticar
from caja.seguridad import destino_seguro, iniciar_sesion, login_requerido

bp = Blueprint("caja", __name__)


@bp.get("/")
def inicio() -> ResponseReturnValue:
    return redirect(url_for("caja.buscar_pedido"))


@bp.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    siguiente = request.values.get("siguiente")
    if g.operador is not None:
        return redirect(destino_seguro(siguiente))

    error = None
    usuario = ""
    if request.method == "POST":
        usuario = request.form.get("usuario", "")
        operador = autenticar(usuario, request.form.get("clave", ""))
        if operador is not None:
            iniciar_sesion(operador)
            return redirect(destino_seguro(siguiente))
        error = "Usuario o clave incorrectos."
    estado = 401 if error else 200
    return render_template("login.html", error=error, usuario=usuario, siguiente=siguiente), estado


@bp.post("/logout")
def logout() -> ResponseReturnValue:
    session.clear()
    return redirect(url_for("caja.login"))


@bp.get("/pedidos/buscar")
@login_requerido
def buscar_pedido() -> ResponseReturnValue:
    codigo = request.args.get("codigo", "")
    if not codigo.strip():
        return render_template("buscar.html", codigo="", error=None)
    pedido = pedidos.buscar_pedido(codigo)
    if pedido is None:
        error = f"No existe el pedido {pedidos.normalizar_codigo(codigo)}."
        return render_template("buscar.html", codigo=codigo, error=error), 404
    return redirect(url_for("caja.detalle_pedido", codigo=pedido.codigo))


@bp.get("/pedidos/<codigo>")
@login_requerido
def detalle_pedido(codigo: str) -> ResponseReturnValue:
    pedido = pedidos.buscar_pedido(codigo)
    if pedido is None:
        abort(404, f"No existe el pedido {pedidos.normalizar_codigo(codigo)}.")
    return render_template("pedido.html", pedido=pedido)
