"""Prueba manual del proveedor de IA (no toca la base de datos).

    IA_MODO=gemini python -m app.ia_prueba "La hamburguesa llegó fría" --tipo mal_estado
    IA_MODO=gemini python -m app.ia_prueba "Llegó aplastada" --tipo mal_estado --foto foto.jpg

Muestra el análisis, cuánto tardó, los tokens y el costo aproximado.
"""

import argparse
import mimetypes
import time
from pathlib import Path

from pydantic import BaseModel

from app.core.config import get_settings
from app.models import TipoReclamo
from app.services.ia import EntradaFoto, EntradaTexto, RespuestaIA, get_proveedor_ia
from app.services.ia_registro import costo_usd

PRODUCTOS_EJEMPLO = ["Combo Clásico", "Nuggets x6", "Sundae de chocolate", "Inca Kola 500 ml"]


def _mostrar[T: BaseModel](titulo: str, inicio: float, respuesta: RespuestaIA[T]) -> None:
    uso = respuesta.uso
    ms = round((time.perf_counter() - inicio) * 1000)
    costo = costo_usd(uso.tokens_entrada, uso.tokens_salida)
    print(f"\n== {titulo} ({uso.modelo}, {ms} ms) ==")
    print(respuesta.resultado.model_dump_json(indent=2))
    print(f"tokens: {uso.tokens_entrada} de entrada, {uso.tokens_salida} de salida; ~US$ {costo}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("descripcion")
    parser.add_argument("--tipo", type=TipoReclamo, default=TipoReclamo.PEDIDO_INCOMPLETO)
    parser.add_argument("--foto", type=Path)
    args = parser.parse_args()

    proveedor = get_proveedor_ia()
    print(f"Proveedor: {proveedor.nombre} (IA_MODO={get_settings().ia_modo.value})")

    inicio = time.perf_counter()
    texto = proveedor.clasificar_texto(
        EntradaTexto(args.descripcion, args.tipo, PRODUCTOS_EJEMPLO, PRODUCTOS_EJEMPLO[:1])
    )
    _mostrar("Texto", inicio, texto)

    if args.foto:
        tipo_mime = mimetypes.guess_type(args.foto.name)[0] or "image/jpeg"
        inicio = time.perf_counter()
        foto = proveedor.analizar_foto(
            EntradaFoto(
                args.foto.read_bytes(),
                tipo_mime,
                args.tipo,
                args.descripcion,
                PRODUCTOS_EJEMPLO[:1],
            )
        )
        _mostrar("Foto", inicio, foto)


if __name__ == "__main__":
    main()
