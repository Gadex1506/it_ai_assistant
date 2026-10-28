# models/text_command_request.py
# =============================================================
# DTO de entrada para procesar un comando que Unity ya transcribio.
#
# Responsabilidad: definir la estructura del dato que Unity envia
# a /assistant/process-text. El audio no viaja: la transcripcion
# ya se hizo antes en /stt/transcribe, y repetirla costaba mas de
# un segundo por comando.
#
# Patron: DTO (Data Transfer Object)
# =============================================================

from typing import Optional
from pydantic import BaseModel, Field


class TextCommandRequest(BaseModel):
    """
    Comando de voz ya transcrito, junto al estado del hogar.

    Attributes:
        text: texto transcrito de lo que dijo el usuario.
        house_context_json: estado de la casa serializado como JSON string,
            igual que en /assistant/process. Puede ir vacio.
        voice: voz de Edge TTS opcional. Usa la del .env si es None.
    """

    text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Texto transcrito del comando del usuario.",
    )
    house_context_json: Optional[str] = Field(
        default=None,
        description="Estado actual de la casa como JSON string.",
    )
    voice: Optional[str] = Field(
        default=None,
        description="Voz de Edge TTS opcional. Usa la del .env si es None.",
    )
