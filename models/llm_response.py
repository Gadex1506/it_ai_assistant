# models/llm_response.py
# =============================================================
# DTO que representa la respuesta del LLM de Groq hacia Unity.
#
# Responsabilidad: definir la estructura del dato que la
# infraestructura del LLM devuelve a la capa de servicios.
#
# Patron: DTO (Data Transfer Object)
# =============================================================

from pydantic import BaseModel, Field
from typing import Optional

# Constantes para los tipos de intencion clasificados por el LLM
INTENT_GENERAL_QUESTION = "general_question"
INTENT_HOME_QUESTION = "home_question"
INTENT_HOME_ACTION = "home_action"

class HomeAction(BaseModel):
    """
    Accion del hogar extaida por el LLM.

    Replica el formato de comando que ya funcionaba en Unity:
        LUZ:Habitacion:Estado, 
        TODAS_LUCES:Estado, 
        TEMP:valor, 
        MOVER:Habitacion.
    Ahora tipado con Pydantic en lugar de un string parseado.

    Attributes:
        type: tipo de accion. Valores: LUZ, TODAS_LUCES, TEMP, MOVER.
        room: habitacion objetivo. None si no aplica para el caso de las acciones de TODAS_LUCES o TEMP.
        state: estado objetivo para luces. Valores: ON, OFF. None si no aplica.
        value: valor numerico para temperatura. None si no aplica.
    """

    type: str = Field(
        ...,
        description="Tipo de accion: LUZ, TODAS_LUCES, TEMP, MOVER.",
    )
    room: Optional[str] = Field(
        default=None,
        description="Habitacion objetivo. Ejemplo: Sala, Cocina, etc.",
    )
    state: Optional[str] = Field(
        default=None,
        description="Estado para las luces: ON, OFF",
    )
    value: Optional[float] = Field(
        default=None,
        description="Valor para temperatura: 1.0 para subir, -1.0 para bajar.",
    )

class LLMResponse(BaseModel):
    """
    Respuesta del LLM con el texto generado y la intencion clasificada

    Attributes:
        response_text: texto de respuesta generada por el LLM.
            Este es el texto que pasara al TTS.
        intent: intencion clasificada del mensaje del usuario.
            Valores: 'general_question', 'home_question', 'home_action'.
        action: datos de la accion si intent es home_action. None si no aplica.
        processing_time_ms: tiempo que tardo el LLM en responder.
        tokens_used: tokens consumidos en la peticion.
    """

    response_text: str =  Field(
        ...,
        description="Texto de respuesta generada por LLM para pasarsela al TTS.",
    )
    intent: str = Field(
        ...,
        description="Intencion clasificada del mensaje en: general_question, home_question, home_action.",
    )
    action: Optional[HomeAction] = Field(
        default=None,
        description="Accion del hogar si intent es home_action.",
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="Tiempo de procesamiento en milisegundos.",
    )
    tokens_used: Optional[int] = Field(
        default=None,
        description="Tokens consumidos en la peticion al LLM.",
    )