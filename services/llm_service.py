# services/llm_service.py
# =============================================================
# Servicio de procesamiento de lenguaje natural del asistente.
#
# Responsabilidad: Recibe texto transcrito por el STT, orquesta la generacion 
# de respuestas del LLM coordinando el cliente de infraestructura LLM, el historial
# de conversacion y la construccion de la respuesta final.
#
# Patron: Dependency Injection: recibe el cliente LLM como
# dependencia en lugar de crearlo internamente.
#
# Principio D de SOLID: depende de BaseLLMClient que es la abstraccion, mas
# no de GroqClient que es la implementacion concreta.
# =============================================================

from infrastructure.llm.base_llm_client import BaseLLMClient
from models.llm_request import LLMRequest, HouseContext
from models.llm_response import LLMResponse

# Numero maximo de turnos de conversacion a mantener en historial.
# Cada turno incluye un mensaje del usuario y una respuesta del asistente.
# Mantener demasiado turnos aumenta el uso de TOKENS innecesariamente.
MAX_CONVERSATION_TURNS = 5

# Numero de mensajes por turno (usuario + asistente = 2)
MESSAGES_PER_TURN = 2

class LLMService:
    """
    Servicio de logica de negocio para procesamiento de lenguaje natural.
    
    Orquesta la generacion de respuestas del LLM usando el cliente
    inyectado. Mantiene el historial de conversacion para que el
    asistente recuerde el contexto entre turnos consecutivos.

    No conoce los detalles de nungun proveedor LLM especifico.
    Solo conoce el contrato BaseLLMClient.

    Attributes:
        _llm_client: cliente LLM que implementa BaseLLMClient.
        _conversation_history: historial de mensajes de la sesion actual.
    """

    def __init__(self, llm_client: BaseLLMClient) -> None:
        """
        Inicializa el servicio con el cliente LLM inyectado.

        Args:
            llm_client: implementacion de BaseLLMClient a usar.
                Puede ser GroqClient u otro proveedor.
        """
        self._llm_client = llm_client
        self._conversation_history: list[dict] = []

    def process_message(
        self,
        user_text: str,
        house_context: HouseContext,
    ) -> LLMResponse:
        """
        Procesa un mensaje del usuario y genera la respuesta del asistente.

        Construye el LLMRequest con el texto, el contexto del hogar
        y el historial de conversacion. Delega al cliente LLM y
        actualiza el historial con el nuevo intercambio.

        Args:
            user_text: texto transcrito por el STT (Whisper) que el usuario dijo.
            house_context: estado actual del hogar enviado por el cliente (Unity).

        Returns:
            LLMResponse con la intencion del comando, respuesta en texto y accion opcional.

        Raises:
            RuntimeError: si el cliente LLM falla al generar la respuesta.
        """
        request = LLMRequest(
            user_text=user_text,
            house_context=house_context,
            conversation_history=self._conversation_history.copy(),
        )

        try:
            response = self._llm_client.chat(request)
        except Exception as error:
            raise RuntimeError(
                f"Error al procesar mensaje con el proveedor "
                f"'{self._llm_client.get_provider_name()}': {error}"
            ) from error
        
        self._update_conversation_history(user_text, response.response_text)

        return response
    
    def clear_conversation_history(self) -> None:
        """
        Limpia el historial de conversacvion de la sesion actual.

        Unity puede llamar a este metodo cuando el usuario
        termina una sesion de conversacion para empezar
        una nueva sin contexto previo.

        Returns:
            None.
        """
        self._conversation_history = []

    def get_conversation_history(self) -> list[dict]:
        """
        Retorna una copia del historial de conversacion actual.
        
        Returns:
            Lista de mensajes del historial en formato OpenAI.
        """
        return self._conversation_history.copy()
    
    def get_active_provider(self) -> str:
        """
        Retorna el nombre del proveedor LLM actualmente activo.

        Returns:
            Nombre del proveedor. Ejemplo: 'groq'.
        """
        return self._llm_client.get_provider_name()
    
    def get_active_model(self) -> str:
        """
        Retorna el nombre del modelo LLM actualmente activo.

        Returns:
            Nombre del modelo. Ejemplo: 'llama-4-scout-17b'.
        """
        return self._llm_client.get_model_name()
    
    def _update_conversation_history(
        self,
        user_text: str,
        assistant_response: str,
    ) -> None:
        """
        Agrega el ultimo intercambio de mensajes, al historial y lo mantiene
        dentro del limite de turnos configurado.
        
        Agregar el intercambio al historial, permite que en el
        siguiente mensaje, el LLM tenga contexto de lo que se
        dijo antes. Por ejemplo, si el usuario dijo "enciende
        la luz de la sala" y luego dice "y la de la cocina",
        el LLM puede llegar a inferir que se refiere a encender la luz
        de la cocina gracias al historial.

        El historial se limita a MAX_CONVERSATION_TURNS turnos
        para controlar el uso de tokens y la latencia.

        Args:
            user_text: mensaje del usuario en este turno.
            assistant_response: respuesta del asistente en este turno.

        Returns:
            None.
        """
        self._conversation_history.append(
            {"role": "user", "content": user_text}
        )
        self._conversation_history.append(
            {"role": "assistant", "content": assistant_response}
        )

        # Mantener solo los ultimos MAX_CONVERSATION_TURNS turnos
        max_messages = MAX_CONVERSATION_TURNS * MESSAGES_PER_TURN
        if len(self._conversation_history) > max_messages:
            self._conversation_history = \
                self._conversation_history[-max_messages:]