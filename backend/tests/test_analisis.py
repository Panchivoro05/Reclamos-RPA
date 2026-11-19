"""Análisis antes de decidir: controles de la IA, foto repetida y su paso por el procesamiento."""

import io
import random
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import EstadoReclamo, LlamadaIA, OperacionIA, PoliticaAntifraude, TipoReclamo
from app.services.almacenamiento import AlmacenamientoLocal
from app.services.analisis import AnalisisIA, controles_ia, distancia, hash_foto
from app.services.bot import EjecutorBotSimulado
from app.services.ia import (
    AnalisisFoto,
    AnalisisTexto,
    EntradaFoto,
    EntradaTexto,
    ErrorIA,
    ProveedorSimulado,
)
from app.services.procesamiento import Resultado, procesar_reclamo
from tests.test_procesamiento import leer, nuevo_reclamo, un_combo
from tests.utils import item_id

UMBRAL = Decimal("0.70")


def _texto(tipo: TipoReclamo | None, confianza: float = 0.9) -> AnalisisTexto:
    return AnalisisTexto(tipo_detectado=tipo, confianza=confianza, explicacion="Explicación.")


def _foto(
    *, es_comida: bool = True, coherente: bool = True, confianza: float = 0.9
) -> AnalisisFoto:
    return AnalisisFoto(
        es_comida=es_comida, coherente=coherente, descripcion="Lo que se ve.", confianza=confianza
    )


def _fallidos(analisis: AnalisisIA, tipo: TipoReclamo = TipoReclamo.MAL_ESTADO) -> list[str]:
    return [c.detalle for c in controles_ia(tipo, analisis, UMBRAL) if not c.aprobado]


# ---------- Controles (funciones puras) ----------


def test_ia_confirma_el_tipo_y_la_foto() -> None:
    controles = controles_ia(
        TipoReclamo.MAL_ESTADO, AnalisisIA(_texto(TipoReclamo.MAL_ESTADO), _foto()), UMBRAL
    )

    assert [(c.nombre, c.aprobado) for c in controles] == [("ia_texto", True), ("ia_foto", True)]


def test_sin_foto_solo_hay_control_de_texto() -> None:
    controles = controles_ia(
        TipoReclamo.DEMORA, AnalisisIA(_texto(TipoReclamo.DEMORA), None), UMBRAL
    )

    assert [c.nombre for c in controles] == ["ia_texto"]


@pytest.mark.parametrize(
    ("analisis", "motivo"),
    [
        (AnalisisIA(_texto(TipoReclamo.MAL_ESTADO, 0.5), None), "no pudo confirmar"),
        (AnalisisIA(_texto(None, 0.95), None), "no pudo confirmar"),
        (AnalisisIA(_texto(TipoReclamo.DEMORA), None), "corresponde a demora y no a mal_estado"),
        (
            AnalisisIA(_texto(TipoReclamo.MAL_ESTADO), _foto(es_comida=False)),
            "no muestra comida",
        ),
        (
            AnalisisIA(_texto(TipoReclamo.MAL_ESTADO), _foto(coherente=False)),
            "no respalda el reclamo",
        ),
        (
            AnalisisIA(_texto(TipoReclamo.MAL_ESTADO), _foto(confianza=0.4)),
            "no respalda el reclamo",
        ),
    ],
)
def test_ia_lleva_a_revision_humana(analisis: AnalisisIA, motivo: str) -> None:
    fallidos = _fallidos(analisis)

    assert len(fallidos) == 1
    assert motivo in fallidos[0]


# ---------- Hash perceptual ----------


def _imagen(semilla: int, tamano: int = 128, formato: str = "PNG") -> bytes:
    """Imagen propia de cada semilla: fondo y elipses de colores (como una foto, sin ruido fino)."""
    azar = random.Random(semilla)

    def color() -> tuple[int, int, int]:
        return (azar.randrange(256), azar.randrange(256), azar.randrange(256))

    imagen = Image.new("RGB", (256, 256), color())
    dibujo = ImageDraw.Draw(imagen)
    for _ in range(6):
        x, y = azar.randrange(200), azar.randrange(200)
        ancho, alto = azar.randrange(30, 120), azar.randrange(30, 120)
        dibujo.ellipse((x, y, x + ancho, y + alto), fill=color())
    salida = io.BytesIO()
    opciones = {"quality": 70} if formato == "JPEG" else {}
    imagen.resize((tamano, tamano)).save(salida, formato, **opciones)
    return salida.getvalue()


def test_la_misma_foto_recomprimida_y_achicada_da_casi_el_mismo_hash() -> None:
    original = hash_foto(_imagen(1))
    recomprimida = hash_foto(_imagen(1, tamano=64, formato="JPEG"))

    assert original is not None and recomprimida is not None
    assert distancia(original, recomprimida) <= 6


def test_fotos_distintas_dan_hashes_lejanos() -> None:
    uno, otro = hash_foto(_imagen(1)), hash_foto(_imagen(4))

    assert uno is not None and otro is not None
    assert distancia(uno, otro) > 6


def test_un_archivo_que_no_es_imagen_no_tiene_hash() -> None:
    assert hash_foto(b"esto no es una imagen") is None


# ---------- En el procesamiento ----------


def _procesar(reclamo_id: int, ia: Any, carpeta: Any = None, **opciones: Any) -> Resultado:
    with SessionLocal() as session:
        return procesar_reclamo(
            session,
            reclamo_id,
            EjecutorBotSimulado(),
            ia=ia,
            almacenamiento=AlmacenamientoLocal(carpeta) if carpeta else None,
            **opciones,
        )


def _llamadas(reclamo_id: int) -> list[LlamadaIA]:
    """Llamadas del análisis (sin las de redactar mensajes, que se prueban aparte)."""
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(LlamadaIA)
                .where(
                    LlamadaIA.reclamo_id == reclamo_id,
                    LlamadaIA.operacion != OperacionIA.REDACTAR_MENSAJE,
                )
                .order_by(LlamadaIA.id)
            )
        )


def test_reclamo_coherente_pasa_por_la_ia_y_se_resuelve(client: TestClient, datos: None) -> None:
    ia = ProveedorSimulado()
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert _procesar(reclamo_id, ia) == Resultado.RESUELTO
    llamadas = _llamadas(reclamo_id)
    assert [(ll.operacion, ll.exito) for ll in llamadas] == [(OperacionIA.CLASIFICAR_TEXTO, True)]
    assert llamadas[0].resultado is not None
    assert llamadas[0].resultado["tipo_detectado"] == "pedido_incompleto"


def test_a_la_ia_solo_le_llegan_datos_del_reclamo(client: TestClient, datos: None) -> None:
    ia = ProveedorSimulado()
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    _procesar(reclamo_id, ia)

    entrada = ia.entradas_texto[0]
    assert entrada.productos_reclamados == ["1 x Combo Clásico (hamburguesa + papas + gaseosa)"]
    assert "Nuggets x6" in entrada.productos_pedido
    # Nada que identifique al cliente.
    assert "cliente1" not in repr(entrada).lower()


def test_descripcion_que_no_coincide_con_el_tipo_se_escala(client: TestClient, datos: None) -> None:
    bot = EjecutorBotSimulado()
    reclamo_id = nuevo_reclamo(
        client, items=un_combo(client), descripcion="Me trajeron otra hamburguesa en vez del combo"
    )

    with SessionLocal() as session:
        resultado = procesar_reclamo(session, reclamo_id, bot, ia=ProveedorSimulado())

    assert resultado == Resultado.ESCALADO
    reclamo = leer(reclamo_id)
    assert "corresponde a producto_equivocado y no a pedido_incompleto" in str(
        reclamo.motivo_escalamiento
    )
    assert bot.solicitudes == []  # el bot no se lanza


def test_el_umbral_de_confianza_es_configurable(client: TestClient, datos: None) -> None:
    with SessionLocal() as session:
        politica = session.get(PoliticaAntifraude, 1)
        assert politica is not None
        politica.umbral_confianza_ia = Decimal("0.95")  # el simulado responde 0.90
        session.commit()
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert _procesar(reclamo_id, ProveedorSimulado()) == Resultado.ESCALADO
    assert "mínimo 0.95" in str(leer(reclamo_id).motivo_escalamiento)


def test_si_la_ia_falla_se_reintenta_y_luego_sigue(client: TestClient, datos: None) -> None:
    fallas = [ErrorIA("503: alta demanda")]

    def texto(entrada: EntradaTexto) -> AnalisisTexto:
        if fallas:
            raise fallas.pop()
        return _texto(entrada.tipo_elegido)

    ia = ProveedorSimulado(texto=texto)
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert _procesar(reclamo_id, ia, ultimo_intento=False) == Resultado.REINTENTAR
    assert leer(reclamo_id).estado == EstadoReclamo.EN_VALIDACION
    assert _procesar(reclamo_id, ia, intento=2) == Resultado.RESUELTO
    assert [ll.exito for ll in _llamadas(reclamo_id)] == [False, True]
    assert _llamadas(reclamo_id)[0].error == "503: alta demanda"


def test_si_la_ia_falla_en_el_ultimo_intento_se_escala(client: TestClient, datos: None) -> None:
    def texto(_: EntradaTexto) -> AnalisisTexto:
        raise ErrorIA("429: cuota agotada")

    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert _procesar(reclamo_id, ProveedorSimulado(texto=texto)) == Resultado.ESCALADO
    assert "No se pudo completar el análisis con IA: 429: cuota agotada" in str(
        leer(reclamo_id).motivo_escalamiento
    )


def _reclamo_con_foto(client: TestClient, foto: bytes, indice: int = 0) -> int:
    return nuevo_reclamo(
        client,
        tipo="mal_estado",
        descripcion="Llegó aplastado y frío",
        items=[{"pedido_item_id": item_id(client, "BY-000101", indice), "cantidad_afectada": 1}],
        foto=("foto.png", foto, "image/png"),
    )


def test_la_foto_se_analiza_y_si_no_respalda_el_reclamo_se_escala(
    client: TestClient, datos: None, carpeta_fotos: Any
) -> None:
    analizadas: list[EntradaFoto] = []

    def foto(entrada: EntradaFoto) -> AnalisisFoto:
        analizadas.append(entrada)
        return _foto(es_comida=False)

    reclamo_id = _reclamo_con_foto(client, _imagen(2))

    resultado = _procesar(reclamo_id, ProveedorSimulado(foto=foto), carpeta_fotos)

    assert resultado == Resultado.ESCALADO
    assert analizadas[0].contenido == _imagen(2)
    assert analizadas[0].tipo_mime == "image/png"
    assert [ll.operacion for ll in _llamadas(reclamo_id)] == [
        OperacionIA.CLASIFICAR_TEXTO,
        OperacionIA.ANALIZAR_FOTO,
    ]
    assert "no muestra comida" in str(leer(reclamo_id).motivo_escalamiento)


def test_la_misma_foto_en_otro_reclamo_se_escala(
    client: TestClient, datos: None, carpeta_fotos: Any
) -> None:
    primero = _reclamo_con_foto(client, _imagen(3), indice=0)
    assert _procesar(primero, ProveedorSimulado(), carpeta_fotos) == Resultado.RESUELTO
    assert leer(primero).foto_hash is not None

    # Otro reclamo (otro producto del mismo pedido) con la misma foto, recomprimida.
    segundo = _reclamo_con_foto(client, _imagen(3, tamano=96, formato="JPEG"), indice=1)

    assert _procesar(segundo, ProveedorSimulado(), carpeta_fotos) == Resultado.ESCALADO
    assert f"igual (o casi igual) a la del reclamo {leer(primero).codigo}" in str(
        leer(segundo).motivo_escalamiento
    )


def test_una_foto_nueva_no_se_marca_como_repetida(
    client: TestClient, datos: None, carpeta_fotos: Any
) -> None:
    primero = _reclamo_con_foto(client, _imagen(3), indice=0)
    assert _procesar(primero, ProveedorSimulado(), carpeta_fotos) == Resultado.RESUELTO

    segundo = _reclamo_con_foto(client, _imagen(5), indice=1)

    assert _procesar(segundo, ProveedorSimulado(), carpeta_fotos) == Resultado.RESUELTO
