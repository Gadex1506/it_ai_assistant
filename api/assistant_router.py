# api/assistant_router.py
# =============================================================
# Router orquestador del pipeline completo del asistente ARIA.
#
# Responsabilidad: coordinar el pipeline STT -> LLM -> TTS
# en un unico endpoint. El cliente (Unity) envia el audio del usuario
# y recibe el audio de respuesta del asistente mas los
# metadatos de accion en los headers HTTP.
#
# Patron Facade: este router actua como fachada sobre los
# tres subsistemas (STT, LLM, TTS) exponiendo una interfaz
# simple para Unity en lugar de tres endpoints separados.
#
# Patron Factory Method: funciones get_*_service() construyen
# los servicios con sus dependencias desde app.state.
# =============================================================

import os
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi import BackgroundTasks, Request, status
from fastapi.responses import FileResponse
from urllib.parse import quote

# Models
from models.llm_request import HouseContext
from models.llm_response import INTENT_HOME_ACTION
from models.tts_request import TTSRequest
from models.morning_greeting_request import MorningGreetingRequest

# Infrastructure
from infrastructure.tts.edge_tts_client import EdgeTTSClient
from infrastructure.weather.openweather_client import OpenWeatherClient

# Services
from services.stt_service import STTService
from services.llm_service import LLMService
from services.tts_service import TTSService
from services.morning_routine_service import MorningRoutineService

import logging

logger = logging.getLogger("it_ai_assistant")

ROUTER_PREFIX = "/assistant"
ROUTER_TAG = "Assistant Pipeline"

# Voz por defecto si el cliente (Unity) no especifica ninguna
DEFAULT_VOICE = None


# =============================================================
# Factory Methods: Leen servicios desde app.state
# =============================================================

def get_stt_service(request: Request) -> STTService:
    """
    Retorna STTService con el cliente Whisper precargado.
    
    Args:
        request: peticion HTTP actual.

    Returns:
        STTService listo para transcribir audio.
    """
    return STTService(stt_client=request.app.state.stt_client)

def get_llm_service(request: Request) -> LLMService:
    """
    Retorna el LLMService con el historial persistente desde app.state
    
    Args:
        request: peticion HTTP actual.

    Returns:
        LLMService con historial de conversacion.
    """
    return request.app.state.llm_service

def get_tts_service() -> TTSService:
    """
    Construye TTSService con EdgeTTSClient.
    
    TTS no necesita estado persistente entre peticiones
    por lo que se puede crear en cada llamada sin problema.

    Returns:
        TTSService listo para sintetizar voz.
    """
    return TTSService(tts_client=EdgeTTSClient())

router = APIRouter(prefix=ROUTER_PREFIX, tags=[ROUTER_TAG])


# =============================================================
# Endpoint orquestador principal
# =============================================================

@router.post(
    "/process",
    response_class=FileResponse,
    summary="Procesar comando de voz completo",
    description=(
        "Endpoint principal del asistente. Recibe el audio del usuario "
        "desde Unity y ejecuta el pipeline completo STT -> LMM -> TTS. "
        "Devuelve el audio de respuesta del asistente como MP3. "
        "La acción del hogar (si aplica) viene en los headers de la respuesta."
    ),
)
async def process_voice_command(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(
        ...,
        description="Audio del comando de voz del usuario en formato WAV o MP3."
    ),
    voice: str | None = None,
    language: str | None = None,
    house_context_json: str | None = None,
    stt_service: STTService = Depends(get_stt_service),
    llm_service: LLMService = Depends(get_llm_service),
    tts_service: TTSService = Depends(get_tts_service),
):
    """
    Orquesta el pipeline completo de ARIA STT -> LMM -> TTS.
    
    Recibe el audio del usuario, lo transcribe con Whisper,
    procesa el texto con Groq para clasifica la intencion y
    generar la respuesta, sintetiza la respuesta con Edge TTS
    y devuelve el audio de respuesta al usuario.

    La accion del hogar (si intent es home_action) viene en
    los headers HTTP de la respuesta para que Unity pueda
    leerla y ejecutar la accion correspondiente en la casa.

    Args:
        background_tasks: gestor de tareas en segundo plano.
        audio_file: archivo de audio del comando del usuario.
        voice: voz de Edge TTS opcional, Usa la del .env si es None.
        language: idioma para Whisper opcional. Detecta automaticamente si es None.
        house_context_json: estado de la casa serializado como JSON string.
            Unity lo envia como form field junto al audio.
        stt_service: servicio STT inyectado desde app.state.
        llm_service: servicio LLM inyectado desde app.state.
        tts_service: servicio TTS inyectado.

    Returns:
        FileResponse con el audio MP3 de la respuesta del asistente.
        Headers con la intencion y accion del hogar si aplica.

    Raises:
        HTTPException 400: si el audio esta vacio o el formato es invalido.
        HTTPException 503: si alguno de los servicios externos falla.
    """

    # ── PASO 1: Leer el audio enviado por Unity ───────────────
    audio_bytes = await audio_file.read()

    # TEMPORAL — guardar copia para diagnostico, borrar despues
    debug_path = os.path.join("temp_audio", "DEBUG_received_audio.wav")
    with open(debug_path, "wb") as f:
        f.write(audio_bytes)
    logger.info(f"[DEBUG] Audio recibido: {len(audio_bytes)} bytes, guardado en {debug_path}")

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo de audio esta vacio.",
        )
    
    # ── PASO 2: Parsear el contexto del hogar ─────────────────
    house_context = _parse_house_context(house_context_json)

    # ── PASO 3: STT - transcribir el audio a texto ────────────
    try:
        stt_result, audio_temp_path = stt_service.transcribe_audio(
            audio_bytes=audio_bytes,
            language=language,
        )
        logger.info(f"[DEBUG] STT transcribio: '{stt_result.text}' (idioma: {stt_result.language})")
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error en transcripcion de voz (STT): {error}",
        )
    finally:
        # Eliminar el audio temporal del STT en segundo plano
        if 'audio_temp_path' in locals():
            background_tasks.add_task(_delete_file, audio_temp_path)
    
    # ── PASO 4: LLM - clasificar intencion y generar respuesta ─
    try:
        llm_response = llm_service.process_message(
            user_text=stt_result.text,
            house_context=house_context,
        )
    except RuntimeError as error:
        logger.error(f"[DEBUG] Fallo en LLM: {error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error en procesamiento de lenguaje (LLM): {error}",
        )
    
    # ── PASO 5: TTS - sintetizar la respuesta en audio ────────
    tts_request = TTSRequest(
        text=llm_response.response_text,
        voice=voice,
    )

    try:
        _, tts_audio_path = await tts_service.synthesize(tts_request)
    except RuntimeError as error:
        logger.error(f"[DEBUG] Fallo en TTS: {error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error en sintesis de voz (TTS): {error}",
        )
    
    # Programa eliminacion del audio TTS de respuesta despues de enviarlo a Unity
    background_tasks.add_task(_delete_file, tts_audio_path)

    # ── PASO 6: Construir headers con la accion del hogar ─────
    response_headers = _build_response_headers(llm_response)

    return FileResponse(
        path=tts_audio_path,
        media_type="audio/mpeg",
        filename="response.mp3",
        headers=response_headers,
    )

@router.post(
    "/morning-greeting",
    response_class=FileResponse,
    summary="Saludo matutino con el clima",
    description=(
        "Genera el saludo matutino de ARIA con la info del clima actual de Bogotá. "
        "Unity llama a este endpoint al abrir la aplicación una vez por día. "
        "Devuelve el audio MP3 con el saludo dinámico de ARIA."
    ),
)
async def morning_greeting(
    request: MorningGreetingRequest,
    background_tasks: BackgroundTasks,
    tts_service: TTSService = Depends(get_tts_service),
):
    """
    Genera el saludo matutino dinamico de ARIA.
    
    Consulta el clima actual de Bogota en OpenWeatherMap,
    construye el texto del saludo con el nombre del usuario,
    la hora y el clima, y lo sintetiza con la voz de ARIA.

    Unity reproduce primero el audio pregrabado de bienvenida
    y luego el audio que devuelve este endpoint, creando una
    experiencia de transicion entre la voz grabada y ARIA.

    Args:
        request: MorningGreetingRequest con nombre del usuario y voz opcional.
        background_tasks: gestor de tareas en segundo plano de FastAPI
        tts_service: servicio TTS inyectado,

    Returns:
        FileResponse con el audio MP3 del saludo de ARIA.

    Raise:
        HTTPException 503: si el TTS o el clima no estan disponibles.
    """
    # Construir el texto del saludo con el clima actual
    weather_client = OpenWeatherClient()
    routine_service = MorningRoutineService(weather_client=weather_client)

    greeting_text = routine_service.build_greeting_text(
        user_name=request.user_name,
    )

    # Sintetizar el saludo con la voz de ARIA
    tts_request = TTSRequest(
        text=greeting_text,
        voice=request.voice,
    )

    try:
        # Sintetizar el saludo
        _, audio_path = await tts_service.synthesize(tts_request)
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error al sintetizar el saludo: {error}",
        )
    
    # Eliminar en segundo plano el audio del saludo generado por ARIA
    # despues de haberlo enviado al cliente (Unity)
    background_tasks.add_task(_delete_file, audio_path)

    return FileResponse(
        path=audio_path,
        media_type="audio/mpeg",
        filename="morning_greeting.mp3",
        headers={
            "X-Greeting-Text": quote(greeting_text),
        },
    )


@router.get(
    "/health",
    summary="Estado del pipeline completo",
    description="Verifica que los tres subsistemas están funcionando.",
)
def health_check(
    request: Request,
    stt_service: STTService = Depends(get_stt_service),
    llm_service: LLMService = Depends(get_llm_service),
):
    """
    Valida el estado de los tres subsitemas del pipeline
    
    Args:
        request: peticion HTTP actual.
        stt_serivice: servicio STT inyectado.
        llm_serivce: servicio LLM inyectado.

    Returns:
        Dict con el estado de cada subsitemas.
    """
    return {
        "status": "ok",
        "pipeline": {
            "stt": {
                "engine": stt_service.get_active_engine(),
                "status": "stt_service ok",
            },
            "llm": {
                "provider": llm_service.get_active_provider(),
                "model": llm_service.get_active_model(),
                "status": "llm_service ok",
            },
            "tts": {
                "engine": "edge_tts",
                "status": "tts ok",
            },
        },
    }



# =============================================================
# Funciones de soporte
# =============================================================

def _parse_house_context(house_context_json: str | None) -> HouseContext:
    """
    Parsea el JSON del contexto de la casa enviado por el cliente (Unity).
    
    Unity envia el estado de la casa como un JSON string en el
    form data junto al archivo de audio. Si no se envia contexto
    o el JSON es invalido, se usa un contexto por defecto.

    Args:
        house_context_json: estado de la casa como JSON string o None.

    Returns:
        HouseContext con los datos del hogar o valores por defecto.
    """
    if not house_context_json:
        return HouseContext()
    
    try:
        context_data = json.loads(house_context_json)
        return HouseContext(**context_data)
    except (json.JSONDecodeError, ValueError):
        return HouseContext()

def _build_response_headers(llm_response) -> dict:
    """
    Construye los headers HTTP con la informacion de la accion del hogar.

    Unity lee estos headers para saber si debe ejecutar una accion
    en la casa y que accion ejecutar. Usar headers permite devolver
    el audio y lo metadatos en una sola respuesta HTTP sin
    necesidad de un endpoint adicional.

    Los valores de texto (response_text, action.room) se codifican
    con URL encoding porque los headers HTTP solo soportan Latin-1
    de forma nativa. Sin esta codificacion, caracteres como 'ñ' o
    tildes llegan corruptos al cliente, ya que Unity decodifica los
    headers asumiendo UTF-8.

    Args:
        llm_response: LLMResponse con la intencion y accion del LLM.
    
    Returns:
        Diccionario de headers HTTP con la informacion de la accion.
    """
    headers = {
        "X-Intent": llm_response.intent,
        "X-Response-Text": quote(llm_response.response_text),
    }

    if llm_response.intent == INTENT_HOME_ACTION and llm_response.action:
        action = llm_response.action
        headers["X-Action-Type"] = action.type
        headers["X-Action-Room"] = quote(action.room) if action.room else "null"
        headers["X-Action-State"] = action.state or "null"
        headers["X-Action-Value"] = str(action.value) if action.value is not None else "null"

    return headers

def _delete_file(file_path: str) -> None:
    """
    Elimina un archivo temporal del disco como tarea en segundo plano.
    
    Args:
        file_path: ruta del archivo a eliminar.

    Returns:
        None.
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError as error:
        print(f"Adevertencia: no se pudo eliminar {file_path}: {error}")