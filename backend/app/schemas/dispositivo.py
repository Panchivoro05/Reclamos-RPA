from pydantic import BaseModel, Field

from app.models import PlataformaDispositivo

# Formato de los tokens de Expo: ExponentPushToken[xxxx] (o ExpoPushToken[xxxx]).
PATRON_TOKEN_EXPO = r"^Expo(nent)?PushToken\[[A-Za-z0-9_\-]+\]$"


class DispositivoEntrada(BaseModel):
    token: str = Field(pattern=PATRON_TOKEN_EXPO, max_length=255)
    plataforma: PlataformaDispositivo
