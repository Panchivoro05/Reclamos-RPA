from pydantic import BaseModel, ConfigDict


class ClienteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nombre: str
    telefono_whatsapp: str | None
