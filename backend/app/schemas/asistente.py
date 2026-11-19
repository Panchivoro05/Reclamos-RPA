from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MensajeChatEntrada(BaseModel):
    rol: Literal["cliente", "asistente"]
    texto: str = Field(min_length=1, max_length=1000)


class ConsultaAsistente(BaseModel):
    """La conversación la guarda la app y la envía completa: el backend no guarda chats."""

    mensajes: list[MensajeChatEntrada] = Field(min_length=1, max_length=30)

    @field_validator("mensajes")
    @classmethod
    def termina_con_el_cliente(cls, mensajes: list[MensajeChatEntrada]) -> list[MensajeChatEntrada]:
        if mensajes[-1].rol != "cliente":
            raise ValueError("El último mensaje debe ser del cliente")
        return mensajes


class RespuestaAsistenteOut(BaseModel):
    respuesta: str
