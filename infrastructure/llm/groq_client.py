# infrastructure/llm/groq_client.py
# =============================================================
# Implementacion del cliente LLM usando la API de Groq.
#
# Responsabilidad: construir los mensajes para el LLM,
# llamar a la API de Groq y parsear la respuesta JSON
# en un LLMResponse tipado.
#
# Patron: Strategy. Implementacion concreta de BaseLLMClient.
# Patron: Facade. Esconde la complejidad de la API de Groq
# y del parsing de JSON detras de un metodo simple.
#
# Principio S de SOLID: cada metodo privado tiene una
# responsabilidad unica y bien definida.
# =============================================================

import json
import time
import httpx

# LLM Infrastructure
from infrastructure.llm.base_llm_client import BaseLLMClient

# LLM Models
from models.llm_request import LLMRequest, HouseContext
from models.llm_response import LLMResponse, HomeAction
from models.llm_response import(
    INTENT_GENERAL_QUESTION,
    INTENT_HOME_QUESTION,
    INTENT_HOME_ACTION,
)

# LLM parameters configs
from config.settings import settings

# Timeout en segundos para las peticiones a la API de Groq
REQUEST_TIMEOUT_SECONDS = 30

PROVIDER_NAME = "groq"

class GroqClient(BaseLLMClient):
    """
    Cliente LLM usando la API de Groq con Llama 4 Scout.
    
    Construye un prompt estructurado que en una sola llamada
    clasifica la intencion del usuario, genera la respuesta
    en texto y extrae el comando tecnico del hogar si aplica.

    El LLM responde siempre en JSON para facilitar el parsing
    y eliminar ambiguedades en la interpretacion de la respuesta.

    Attributes:
        _headers: cabeceras HTTP con autenticacion para Groq.
    """

    def __init__(self) -> None:
        """
        Inicializa el cliente con las credenciales de Groq
        leidas desde la configuracion centralizada.
        """
        self._headers = {
            "Authorization": f"Bearer {settings.groq.api_key}",
            "Content-Type": "application/json",
        }
    
    def chat(self, request: LLMRequest) -> LLMResponse:
        """
        Envia una peticion a Groq y retorna la respuesta procesada.

        Construye el system prompt con el contexto del hogar,
        llama a la API de Groq y parsea la respuesta JSON
        en un LLMResponse tipado con Pydantic.

        Args:
            request: LLMRequest con texto, contexto del hogar
                e historial de conversacion.

        Returns:
            LLMResponse: con intencion, respuesta y accion opcional.

        Raises:
            RuntimeError: si la API de Groq devuelve un error HTTP.
            ValueError: si la respuesta no tiene formato JSON valido.
        """
        start_time = time.perf_counter()

        system_prompt = self._build_system_prompt(request.house_context)
        messages = self._build_messages(
            system_prompt=system_prompt,
            user_text=request.user_text,
            conversation_history=request.conversation_history,
        )

        raw_response = self._call_groq_api(messages)
        processing_time_ms = (time.perf_counter() - start_time) * 1000

        llm_response = self._parse_response(raw_response, processing_time_ms)

        return llm_response
    
    def get_model_name(self):
        """
        Retorna el nombre del modelo LLM activo.

        Returns:
            Nombre del modelo configurado en settings
        """
        return settings.groq.model
    
    def get_provider_name(self):
        """
        Retorna el nombre del proveedor del LLM.

        Returns:
            String 'groq'.
        """
        return PROVIDER_NAME
    
    def _build_system_prompt(self, house_context: HouseContext) -> str:
        """
        Construye el system prompt con el contexto actual del hogar.
        
        El prompt instruye al LLM para que en UNA SOLA RESPUESTA:
        1. Clasifique la intencion del usuario
        2. Genera el texto de respuesta para el TTS
        3. Extraiga el comando tecnico si es una accion del hogar

        Esto reemplaza las dos llamadas separadas que se hacian
        en la implementacion original en Unity, provocando asi,
        una baja favorable en la latencia.

        Args:
            house_context: estado actual del hogar desde Unity.

        Returns:
            System prompt completo como string.
        """
        display_names_list = ", ".join(house_context.room_display_names) \
            if house_context.room_display_names \
            else "No hay habitaciones registradas"

        recognizable_names_list = ", ".join(house_context.available_rooms) \
                    if house_context.available_rooms \
                    else "No hay habitaciones registradas"
        
        return f"""Eres Emma, un asistente de voz inteligente para el hogar. \
            Eres amable, amigable, concisa y directa. Siempre respondes en español.

            ESTADO ACTUAL DEL HOGAR:
            - Luces encendidas: {house_context.lights_on_count} de {house_context.lights_total}
            - Temperatura: {house_context.temperature_celsius}°C
            - Habitacion actual: {house_context.current_room}
            - Numero total de habitaciones: {house_context.rooms_total}
            - Nombres principales de las habitaciones (usa ESTA lista cuando el \
            usuario pida que le nombres las habitaciones, NO menciones alias a \
            menos que el usuario pregunte especificamente por formas alternativas \
            de llamar una habitacion): {display_names_list}
            - Nombres reconocibles adicionales, solo para tu uso interno al \
            interpretar lo que dice el usuario, NUNCA los recites en tus \
            respuestas: {recognizable_names_list}

            INSTRUCCIONES:
            Analiza el mensaje del usuario y responde UNICAMENTE con un objeto JSON valido \
            con esta estructura exacta, sin texto adicional antes o despues:

            {{
            "intent": "<general_question|home_question|home_action>",
            "response_text": "<texto que diras en voz alta, breve, amigable y amable>",
            "action": {{
                "type": "<LUZ|TODAS_LUCES|TEMP|MOVER>",
                "room": "<nombre de habitacion o null>",
                "state": "<ON|OFF o null>",
                "value": <numero o null>
            }}
            }}

            REGLAS DE INTENCION:
            - general_question: el usuario hace una pregunta no relacionada con el hogar
            - home_question: el usuario pregunta sobre el estado de la casa
            - home_action: el usuario pide ejecutar una accion en el hogar

            REGLAS DE ACCION (solo cuando intent es home_action):
            - LUZ: encender o apagar una luz especifica. room=habitacion, state=ON u OFF
            - TODAS_LUCES: encender o apagar todas las luces. room=null, state=ON u OFF
            - TEMP: subir o bajar la temperatura. room=null, state=null, value=1.0 o -1.0
            - MOVER: mover el agente a una habitacion. room=habitacion, state=null, value=null

            REGLAS DE MAPEO SEMANTICO:
            - Si el usuario dice "baño", mapear a la habitacion que corresponda en la lista
            - Usar sinonimos para identificar la habitacion correcta de la lista disponible
            - Si la accion no es clara, usar intent=general_question y pedir aclaracion

            CUANDO intent NO es home_action: el campo "action" debe ser null.

            EJEMPLOS:
            Usuario: "Enciende la luz de la sala"
            {{"intent":"home_action","response_text":"Entendido, encendiendo la luz de la sala.","action":{{"type":"LUZ","room":"Sala","state":"ON","value":null}}}}

            Usuario: "Apaga todo"
            {{"intent":"home_action","response_text":"Apagando todas las luces.","action":{{"type":"TODAS_LUCES","room":null,"state":"OFF","value":null}}}}

            Usuario: "Ve a la cocina"
            {{"intent":"home_action","response_text":"Moviendome a la cocina.","action":{{"type":"MOVER","room":"Cocina","state":null,"value":null}}}}

            Usuario: "Cuantas luces hay encendidas"
            {{"intent":"home_question","response_text":"Actualmente hay {house_context.lights_on_count} luces encendidas de {house_context.lights_total} en total.","action":null}}

            Usuario: "Como estas"
            {{"intent":"general_question","response_text":"Estoy muy bien, lista para ayudarte. En que puedo asistirte?","action":null}}"""
    
    def _build_messages(
        self,
        system_prompt: str,
        user_text: str,
        conversation_history: list[dict],
    ) -> list[dict]:
        """
        Construye una lista de mensajes para la API de Groq.
        
        Combina el system prompt, el historial de conversacion
        y el mensaje actual del usuario en el formato que
        espera la API compatible con OpenAI.

        Args:
            system_prompt: instrucciones del sistema con contexto del hogar.
            usert_text: texto actual del usuario.
            conversation_history: mensajes anteriores de la conversacion.

        Returns:
            Lista de mensajes en formato OpenAI chat completions.
        """
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_text})
        return messages
    
    def _call_groq_api(self, messages: list[dict]) -> dict:
        """
        Llama a la API de Groq y retorna la respuesta cruda.

        Usa httpx en modo sincrono porque el servicio LLM
        se integra en un contexto sincrono desde el servicio.
        
        Args:
            messages: lista de mensajes en formato OpenAI.

        Returns:
            Diccionario con la respuesta completa de la API de Groq.

        Raises:
            RuntimeError: si la API devuelve un codigo de error HTTP.
        """
        payload = {
            "model": settings.groq.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.post(
                url=settings.groq.endpoint,
                headers=self._headers,
                json=payload,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Error de la API de Groq. "
                f"Codigo: {response.status_code}. "
                f"Detalle: {response.text}"
            )
        
        return response.json()
    
    def _parse_response(
        self,
        raw_response: dict,
        processing_time_ms: float,
    ) -> LLMResponse:
        """
        Parsea la respuesta cruda de Groq en un LLMResponse tipado.
        
        Extrae el contenido JSON del mensaje de respuesta,
        lo valida con Pydantic y construye el LLMResponse.

        Args:
            raw_response: respuesta completa de la API de Groq.
            processing_time_ms: tiempo total de la peticion en ms.

        Returns:
            LLMResponse tipado y validado con Pydantic.

        Raises:
            ValueError: si el JSON no tiene la estructura esperada.
        """
        content = raw_response["choices"][0]["message"]["content"]
        tokens_used = raw_response.get("usage", {}).get("total_tokens")

        parsed = json.loads(content)

        # Construir HomeAction solo si la intencion es home_action
        action = None
        if parsed.get("intent") == INTENT_HOME_ACTION and parsed.get("action"):
            action_data = parsed["action"]
            action = HomeAction(
                type=action_data.get("type", ""),
                room=action_data.get("room"),
                state=action_data.get("state"),
                value=action_data.get("value"),
            )

        return LLMResponse(
            response_text=parsed.get("response_text", ""),
            intent=parsed.get("intent", INTENT_GENERAL_QUESTION),
            action=action,
            processing_time_ms=round(processing_time_ms, 2),
            tokens_used=tokens_used,
        )