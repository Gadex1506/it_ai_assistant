# models/tts_response.py
# =============================================================
# DTO que representa la respuesta tras una sintesis de voz.
#
# Responsabilidad: definir la estructura del dato que el servidor
# devuelve a Unity confirmando que el audio fue generado.
#
# Patron: DTO (Data Transfer Object)
# =============================================================

from pydantic import BaseModel

class TTSResponse(BaseModel):
    """
    Respuesta del servidor despues de generar el audio con TTS
    
    En el caso de un audio pequenio, el servidor puede devolver
    el audio directamente como bytes (StreamingResponse de FastAPI).
    Este DTO se usa para respuestas de metadatos o errores.

    Attributes:
        success: indica si la generacion de audio fue exitosa.
        message: mensaje descriptivo del resultado.
        voice_used: voz que se uso para generar el audio.
        audio_duration_ms: duracion aproximada del audio en ms.
            None si no se pudo calcular la duracion.
    """
    success: bool
    message: str
    voice_used: str
    audio_duration_ms: float | None = None