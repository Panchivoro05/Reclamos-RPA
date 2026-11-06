"""Uso: python -m bot_rpa --pedido BY-000101 --solucion reembolso_parcial --monto 10 \\
           --motivo "Faltó una hamburguesa en el pedido" [--visible]

Imprime el resultado en JSON. Código de salida 0 si se registró la compensación.
"""

import argparse
import json
import sys

from bot_rpa.ejecutar import SOLUCIONES, SolicitudBot, resolver_reclamo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bot_rpa", description="Resuelve un reclamo operando SISCAJA."
    )
    parser.add_argument("--pedido", required=True, help="Código del pedido (BY-000101)")
    parser.add_argument("--solucion", required=True, choices=SOLUCIONES)
    parser.add_argument("--motivo", required=True)
    parser.add_argument("--monto", default="", help="Monto en soles (reembolso parcial o cupón)")
    parser.add_argument("--tipo-reclamo", default="")
    parser.add_argument(
        "--items-esperados",
        default="",
        help='JSON: [{"producto": "Hamburguesa Clásica", "cantidad": 1}]',
    )
    parser.add_argument("--total-esperado", default="", help="Total del pedido (82.50)")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--visible", action="store_true", default=None, help="Muestra el navegador")
    modo.add_argument("--oculto", dest="visible", action="store_false", help="Sin ventana")
    args = parser.parse_args(argv)

    try:
        solicitud = SolicitudBot(
            pedido=args.pedido.strip().upper(),
            solucion=args.solucion,
            motivo=args.motivo,
            monto=args.monto,
            tipo_reclamo=args.tipo_reclamo,
            items_esperados=json.loads(args.items_esperados) if args.items_esperados else [],
            total_esperado=args.total_esperado,
        )
    except (ValueError, json.JSONDecodeError) as e:
        parser.error(str(e))

    resultado = resolver_reclamo(solicitud, visible=args.visible)
    print(json.dumps(resultado.a_dict(), ensure_ascii=False, indent=2))
    return 0 if resultado.exito else 1


if __name__ == "__main__":
    sys.exit(main())
