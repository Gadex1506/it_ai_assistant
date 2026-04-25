# models/llm_request.py
# =============================================================
# DTO que representa una peticion desde Unity al LLM de Groq.
#
# Responsabilidad: definir la estructura del mensaje que la
# capa de servicios envia a la infraestructura del LLM.
#
# Patron: DTO (Data Transfer Object)
# =============================================================

from pydantic import BaseModel, Field
from typing import Optional

class HouseContext(BaseModel):
    """
    Estado actual del hogar enviado desde Unity.
    
    Contiene la informacion que el LLM necesita para responder
    preguntas sobre el estado de la casa y tomar decisiones
    sobre las acciones a ejecutar.

    Attributes:
        lights_on_count: numero de luces encendidas actualmente.
        lights_total: numero total de luces en la casa.
        temperature_celsius: temperatura actual del termostato.
        current_room: habitacion donde se encuentra el agente.
        available_rooms: lista de habitaciones disponibles para
            navegar. Nombres en string dinamico (no estaticos)
            para soportar edicion desde el panel web del usuario.
    """
    lights_on_count: int = Field(
        default=0,
        description="Numero de luces encendidas actualmente.",
    )
    lights_total: int = Field(
        default=0,
        description="Numero total de luces en la casa.",
    )
    temperature_celsius: float = Field(
        default=2.0,
        description="Temperatura actual del termostato en Celsius.",
    )
    current_room: str = Field(
        default="Desconocida",
        description="Habitacion donde se encuentra el agente.",
    )
    available_rooms: list[str] = Field(
        default_factory=list,
        description="Lista de habitaciones disponibles para navegar.",
    )

class LLMRequest(BaseModel):
    """
    Peticion al LLM con el texto del usuario y contexto adicional.
    
    Attributes:
        user_text: texto transcrito por Whisper que el usuario dijo.
            Dato obligatorio.
        house_context: estado actual del hogar desde Unity.
        conversation_history: historial de mensajes anteriores para
            para mantener contexto entre turnos.
            Lista de dicts con 'role' y 'content'.
        system_prompt: instrucciones de personalidad del asistente.
            Si es None, el servicio usa el prompt por defecto.
    """

    user_text: str = Field(
        ...,
        min_length=1,
        description="Texto del usuario a procesar por el LLM.",
    )
    house_context: HouseContext = Field(
        default_factory=HouseContext,
        description="Estado actual del hogar enviado desde Unity.",
    )
    conversation_history: list[dict] = Field(
        default_factory=list,
        description="Historial de conversacion para contexto.",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="System prompt personalizado. Usa el por defecto si es None.",
    ) 