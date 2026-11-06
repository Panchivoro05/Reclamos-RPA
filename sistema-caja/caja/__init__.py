"""SISCAJA v2.3: sistema de caja antiguo de BurgerYa.

Simula un sistema interno heredado. Solo tiene interfaz web (HTML + formularios) y
NO expone API: el bot RPA debe operarlo por la pantalla, como lo haría un cajero.
"""

import secrets
from pathlib import Path
from typing import Any

import click
from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

from caja import db, seguridad
from caja.config import Settings
from caja.formato import fecha_lima, soles
from caja.operadores import guardar_operador


def create_app(ajustes: dict[str, Any] | None = None) -> Flask:
    settings = Settings()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key or secrets.token_hex(32),
        DB_PATH=Path(settings.db_path).resolve(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        OPERADOR_USUARIO=settings.operador_usuario,
        OPERADOR_NOMBRE=settings.operador_nombre,
        OPERADOR_CLAVE=settings.operador_clave,
    )
    if ajustes:
        app.config.update(ajustes)

    db.registrar(app)
    app.before_request(seguridad.cargar_operador)
    app.before_request(seguridad.verificar_csrf)
    app.jinja_env.filters["soles"] = soles
    app.jinja_env.filters["fecha"] = fecha_lima
    app.jinja_env.globals["csrf_token"] = seguridad.token_csrf

    from caja.vistas import bp

    app.register_blueprint(bp)

    @app.errorhandler(HTTPException)
    def error_http(error: HTTPException) -> tuple[str, int]:
        return render_template("error.html", error=error), error.code or 500

    @app.cli.command("init-db")
    def init_db() -> None:
        """Crea las tablas y el operador definido en CAJA_OPERADOR_*."""
        conexion = db.conectar(app.config["DB_PATH"])
        try:
            db.crear_esquema(conexion)
            clave = app.config["OPERADOR_CLAVE"]
            if not clave:
                raise click.ClickException(
                    "Define CAJA_OPERADOR_CLAVE en el .env para crear el operador."
                )
            guardar_operador(
                conexion, app.config["OPERADOR_USUARIO"], app.config["OPERADOR_NOMBRE"], clave
            )
        finally:
            conexion.close()
        click.echo(
            f"Base de datos lista en {app.config['DB_PATH']} "
            f"(operador: {app.config['OPERADOR_USUARIO']})."
        )

    return app
