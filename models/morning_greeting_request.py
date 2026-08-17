# models/morning_greeting_request.py
# =============================================================
# DTO para la peticion de saludo matutino.
# =============================================================

from pydantic import BaseModel, Field
from typing import Optional

class MorningGreetingRequest(BaseModel):
    """
    Peticion de saludo diario enviado por Unity.
    
    Unity envia el nombre del usuario autenticado para que
    ARIA lo incluya en el saludo dinamico junto con el clima.

    Arributes:
        user_name: nombre del usuario autenticado. Se es None,
            ARIA usa un saludo generico sin nombre.
        voice: voz de Edge TTS opcional para el saludo.
    """
    user_name: Optional[str] = Field(
        default=None,
        description="Nombre del usuario autenticado. None para saludo generico."
    )
    voice: Optional[str] = Field(
        default=None,
        description="Voz de Edge TTS. Usa la del .env si es None.",
    )