# models/tts_request.py
# =============================================================
# DTO que representa la petición de sintesis de voz.
#
# Responsabilidad: definir y validar la estructura del dato
# que Unity envia al endpoint POST /speak. Si los datos no
# cumplen el contrato, Pydantic rechaza la peticion antes de
# que llegue a la capa de servicios.
#
# Patron: DTO (Data Transfer Object)
# =============================================================

from pydantic import BaseModel, Field
from typing import Optional

class TTSRequest(BaseModel):
    """
    Contrato de entrada para el endpoint de sintesis de voz.

    Unity envia este objeto como JSON en el body de la peticion
    HTTP. Todos los campos con valor por defecto son opcionales,
    Unity solo necesita enviar el texto obligatoriamente.

    Attributes:
        text: texto que el asistente debera de pronunciar
        voice: nombre de la voz de Edge TTS a usar
            Si es None, el servidor usa TTS_DEFAULT_VOICE del .env.
        speed: velocidad de la voz en formato Edge TTS (+10%, -5%, etc).
            Si es None, usa TTS_DEFAULT_SPEED del .env.
        pitch: tono de la voz en formato Edge TTS (+10Hz, -5Hz, etc)
            Si es None, usa TTS_DEFAULT_PITCH del .env.
        language: codigo de idioma para referencia del cliente.
            No afecta la generacion, la voz ya determina el idioma.
    """
    text: str = Field(
        # Los tres puntos significan que este dato es obligatorio que lo pase Unity.
        # De lo contrario Pydantic rechazara esto y dara un error 422.
        ...,
        min_length=1,
        max_length=5000,
        description="Texto a convertir en audio.",
    )
    # Optional[str], significa que el campo puede ser una cadena o None. El valor por defecto es None, 
    # lo que indica que si Unity no lo proporciona, el servidor usará un valor predeterminado definido 
    # en las variables de entorno.
    voice: Optional[str] = Field(
        default=None,
        description="Voz de Edge TTS. Ej: es-CL-CatalinaNeural, en-US-JennyNeural.",
    )
    speed: Optional[str] = Field(
        default=None,
        description="Velocidad de la voz. Ej: +0%, +10%, -5%.",
    )
    pitch: Optional[str] = Field(
        default=None,
        description="Tono de la voz. Ej: +0Hz, +10Hz, -5Hz.",
    )
    language: Optional[str] = Field(
        default=None,
        description="Codigo de idioma informativo. Ej: es-CL, en-US.",
    )

    class Config:
        # Permite documentacion automatica en FastAPI con ejemplos reales.
        json_schema_extra = {
            "examples": [
                {
                    "summary": "Peticion minima (solo texto)",
                    "value": {
                        "text": "Hola, todas las luces están apagadas.",
                    },
                },
                {
                    "summary": "Peticion completa con voz en ingles",
                    "value": {
                        "text": "Hello, all lights are off.",
                        "voice": "en-US-JennyNeural",
                        "speed": "+0%",
                        "pitch": "+0Hz",
                        "language": "en-US",
                    },
                },
            ]
        }