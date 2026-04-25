# models/stt_result.py
# =============================================================
# DTO que representa el resultado de una transcripcion de voz.
#
# Responsabilidad: definir la estructura del dato que la capa
# de infraestructura de Whisper devuelve a la capa de servicios
# tras procesar un archivo de audio del usuario.
#
# Patron: DTO (Data Transfer Object)
# =============================================================

from pydantic import BaseModel, Field

class STTResult(BaseModel):
    """
    Resultado de la transcripcion de audio por Whisper.
    
    Attributes:
        text: texto transcrito del audio del usuario. 
            Los tres puntos significan que el dato es obligatorio.
        language: idioma detectado por Whisper. Ej: 'es', 'en'.
        confidence: nivel de confianza de la transcripcion (0.0 a 1.0).
            None si Whisper no provee este dato en el modelo usado.
        processing_time_ms: tiempo que tardo la transcripcion en ms.
    """

    text: str = Field(
        ...,
        description="Texto transcrito del audio del usuario.",
    )
    language: str = Field(
        ...,
        description="Idioma detectado por Whisper. Ej: 'es', 'en'.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Nivel de confianza de la transcripcion (0.0 a 1.0). None si no esta disponible.",
    )
    processing_time_ms: float | None = Field(
        default=None,
        description="Tiempo de procesamiento en milisegundos.",
    )