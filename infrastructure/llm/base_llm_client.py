# infrastructure/llm/base_llm_client.py
# =============================================================
# Contrato base para todos los clientes de LLM (Large Language Model).
#
# Responsabilidad: definir la interfaz que cualquier cliente
# de modelo de lenguaje debe implementar para ser intercambiable
# en el sistema del asistente de voz del hogar.
#
# Patron: Strategy: este es el contrato de la estrategia LLM.
#
# Principio O de SOLID: agregar un nuevo LLM (OpenAI, Gemini,
# Ollama) solo requiere crear una nueva subclase.
# Principio D de SOLID: las capas superiores dependen de
# esta abstraccion, nunca de GroqClient directamente.
# =============================================================

from abc import ABC, abstractmethod
from models.llm_request import LLMRequest
from models.llm_response import LLMResponse

class BaseLLMClient(ABC):
    """
    Clase abstracta base para clientes de modelos de lenguaje (LLM).
    
    Define el contrato que cualquier LLM debe cumplir para
    ser usado por LLMService. Permite cambiar de Groq a
    OpenAI, Gemini u Ollama sin modificar la logica de negocio.
    """

    @abstractmethod
    def chat(self, request: LLMRequest) -> LLMResponse:
        """
        Envia una peticion al LLM y retorna la respuesta procesada.
        
        Recibe un LLMRequest con el texto del usuario, el historial
        de conversacion, el contexto del hogar y el system prompt.
        Devuelve (retorna) un LLResponse con la intencion clasificada, el
        texto de respuesta y los datos de accion si corresponde.

        Args:
            request: LLMRequest con todos los datos necesarios
                para generar la respuesta del asistente.
        
        Returns:
            LLResponse: con intencion, respuesta y accion opcional.

        Raises:
            RuntimeError: si el LLM falla al generar la respuesta.
            ValueError: si la respuesta del LLM no tiene el formato
                JSON esperado.
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """
        Retorna el nombre del modelo LLM activo respectivamente.
        
        Returns:
            Nombre del modelo. Ejemplo: 'llama-4-scout-17b'.
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Retorna el nombre del proveedor del LLM.
        
        Returns:
            Nombre del proveedor. Ejemplo: 'groq', 'openai'.
        """
        pass