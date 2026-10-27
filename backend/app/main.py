import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errores import ErrorAPI, NoAutenticado

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Mensajes en español para los errores de validación más comunes de Pydantic.
MENSAJES_VALIDACION: dict[str, str] = {
    "missing": "Este campo es obligatorio.",
    "string_too_short": "Debe tener al menos {min_length} caracteres.",
    "string_too_long": "Debe tener como máximo {max_length} caracteres.",
    "enum": "El valor no es válido. Opciones: {expected}.",
    "int_parsing": "Debe ser un número entero.",
}

app = FastAPI(
    title="API de reclamos BurgerYa",
    version="0.1.0",
    description="Registro y seguimiento de reclamos de pedidos de delivery.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    # La sesión viaja en encabezados (X-Dev-User o Authorization), no en cookies.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ErrorAPI)
def manejar_error_api(_: Request, error: ErrorAPI) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if isinstance(error, NoAutenticado) else None
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.mensaje, "codigo": error.codigo},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
def manejar_error_validacion(_: Request, error: RequestValidationError) -> JSONResponse:
    errores = []
    for detalle in error.errors():
        plantilla = MENSAJES_VALIDACION.get(detalle["type"])
        # Pydantic une las opciones con "or": "'a', 'b' or 'c'".
        contexto = {
            clave: str(valor).replace("' or '", "' o '")
            for clave, valor in (detalle.get("ctx") or {}).items()
        }
        mensaje = plantilla.format(**contexto) if plantilla else detalle["msg"]
        campo = ".".join(str(parte) for parte in detalle["loc"] if parte not in ("body", "query"))
        errores.append({"campo": campo, "mensaje": mensaje})
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Revisa los datos del formulario.",
            "codigo": "validacion",
            "errores": errores,
        },
    )


app.include_router(api_router)
