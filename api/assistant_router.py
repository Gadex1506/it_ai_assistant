# api/assistant_router.py
# =============================================================
# Router orquestador del pipeline completo del asistente Mía.
#
# Responsabilidad: coordinar el pipeline STT -> LLM -> TTS.
# Expone dos entradas al mismo pipeline:
#   - /process       recibe AUDIO (hace STT, luego LLM y TTS).
#   - /process-text  recibe TEXTO ya transcrito (salta el STT).
# Unity usa /process-text porque ya transcribio el audio antes
# para detectar el cierre de sesion, y repetir el STT costaba
# mas de un segundo por comando.
#
# Patron Facade: este router actua como fachada sobre los
# tres subsistemas (STT, LLM, TTS) exponiendo una interfaz
# simple para Unity en lugar de tres endpoints separados.
#
# Patron Factory Method: funciones get_*_service() construyen
# los servicios con sus dependencias desde app.state.
#
# Patron Template Method (ligero): _generate_response() es la parte
# comun LLM -> TTS -> headers; cada endpoint solo cambia como
# obtiene el texto del usuario.
# =============================================================

import os
import json
import logging
from contextlib import contextmanager
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi import BackgroundTasks, Request, status
from fastapi.responses import FileResponse

# Models
from models.llm_request import HouseContext
from models.llm_response import INTENT_HOME_ACTION
from models.tts_request import TTSRequest
from models.morning_greeting_request import MorningGreetingRequest
from models.text_command_request import TextCommandRequest

# Infrastructure
from infrastructure.tts.edge_tts_client import EdgeTTSClient
from infrastructure.weather.openweather_client import OpenWeatherClient
from infrastructure.metrics.latency_log import PipelineTimings, latency_logger

# Services
from services.stt_service import STTService
from services.llm_service import LLMService
from services.tts_service import TTSService
from services.morning_routine_service import MorningRoutineService

# Error codes
from api.error_codes import (
    api_error, api_error_from, error_code_of,
    ERR_STT, ERR_LLM, ERR_TTS, ERR_EMPTY_TRANSCRIPTION,
    GROQ_HOST, EDGE_TTS_HOST,
)

logger = logging.getLogger("it_ai_assistant")

ROUTER_PREFIX = "/assistant"
ROUTER_TAG = "Assistant Pipeline"

# Voz por defecto si el cliente (Unity) no especifica ninguna
DEFAULT_VOICE = None

# =============================================================
# Factory Methods: Leen servicios desde app.state
# =============================================================

def get_stt_service(request: Request) -> STTService:
    """Retorna STTService con el cliente Whisper precargado."""
    return STTService(stt_client=request.app.state.stt_client)

def get_llm_service(request: Request) -> LLMService:
    """Retorna el LLMService con el historial persistente desde app.state."""
    return request.app.state.llm_service

def get_tts_service() -> TTSService:
    """
    Construye TTSService con EdgeTTSClient.

    TTS no necesita estado persistente entre peticiones,
    por lo que se puede crear en cada llamada sin problema.
    """
    return TTSService(tts_client=EdgeTTSClient())

router = APIRouter(prefix=ROUTER_PREFIX, tags=[ROUTER_TAG])


# =============================================================
# Registro de latencias
# =============================================================

@contextmanager
def _tracked(timings: PipelineTimings):
    """
    Garantiza que cada peticion deje una fila en el registro de latencias,
    termine bien o mal, y que el estado quede anotado.

    Evita repetir el try/except/finally en cada endpoint.
    """
    try:
        yield
    except HTTPException as exc:
        timings.status = error_code_of(exc)
        raise
    except Exception:
        timings.status = "unexpected_error"
        raise
    finally:
        timings.finish()
        latency_logger.write(timings)


# =============================================================
# Endpoints orquestadores
# =============================================================

@router.post(
    "/process",
    response_class=FileResponse,
    summary="Procesar comando de voz completo (audio)",
    description=(
        "Recibe el audio del usuario y ejecuta el pipeline completo "
        "STT -> LLM -> TTS. Devuelve el audio de respuesta como MP3. "
        "La accion del hogar (si aplica) viene en los headers."
    ),
)
async def process_voice_command(
    http_request: Request,
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
    Pipeline completo desde audio: STT -> LLM -> TTS.

    Args:
        http_request: peticion HTTP (lee X-Request-Id).
        background_tasks: tareas en segundo plano para borrar temporales.
        audio_file: audio del comando del usuario.
        voice: voz de Edge TTS opcional.
        language: idioma para Whisper opcional.
        house_context_json: estado de la casa como JSON string.
        stt_service, llm_service, tts_service: servicios inyectados.

    Returns:
        FileResponse con el MP3 de respuesta y la accion en headers.

    Raises:
        HTTPException 400: audio vacio.
        HTTPException 422: no se detecto voz.
        HTTPException 503/429: falla de STT, LLM o TTS.
    """
    timings = PipelineTimings(
        request_id=http_request.headers.get("x-request-id"),
        language=language,
    )

    with _tracked(timings):
        audio_bytes = await audio_file.read()
        timings.audio_bytes = len(audio_bytes)

        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo de audio esta vacio.",
            )

        house_context = _parse_house_context(house_context_json)

        # STT: transcribir el audio a texto
        audio_temp_path = None
        try:
            with timings.stage("stt"):
                stt_result, audio_temp_path = stt_service.transcribe_audio(
                    audio_bytes=audio_bytes,
                    language=language,
                )
            timings.stt_infer_ms = getattr(stt_result, "processing_time_ms", None)
            timings.stt_chars = len(stt_result.text or "")
            logger.info(f"[DEBUG] STT transcribio: '{stt_result.text}' (idioma: {stt_result.language})")
        except RuntimeError as error:
            raise api_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                ERR_STT,
                f"Error en transcripcion de voz (STT): {error}",
            )
        finally:
            if audio_temp_path:
                background_tasks.add_task(_delete_file, audio_temp_path)

        # Silencio o ruido: no tiene sentido llamar al LLM
        if not stt_result.text or not stt_result.text.strip():
            raise api_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ERR_EMPTY_TRANSCRIPTION,
                "No se detecto voz en el audio.",
            )

        return await _generate_response(
            user_text=stt_result.text,
            house_context=house_context,
            voice=voice,
            timings=timings,
            background_tasks=background_tasks,
            llm_service=llm_service,
            tts_service=tts_service,
        )


@router.post(
    "/process-text",
    response_class=FileResponse,
    summary="Procesar comando ya transcrito (texto)",
    description=(
        "Igual que /process pero el cliente ya transcribio el audio. "
        "Salta el STT y ejecuta LLM -> TTS. Devuelve el MP3 de respuesta."
    ),
)
async def process_text_command(
    body: TextCommandRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    llm_service: LLMService = Depends(get_llm_service),
    tts_service: TTSService = Depends(get_tts_service),
):
    """
    Pipeline desde texto: LLM -> TTS.

    Args:
        body: TextCommandRequest con el texto, el contexto y la voz.
        http_request: peticion HTTP (lee X-Request-Id).
        background_tasks: tareas en segundo plano.
        llm_service, tts_service: servicios inyectados.

    Returns:
        FileResponse con el MP3 de respuesta y la accion en headers.

    Raises:
        HTTPException 422: texto vacio tras quitar espacios.
        HTTPException 503/429: falla de LLM o TTS.
    """
    timings = PipelineTimings(request_id=http_request.headers.get("x-request-id"))

    with _tracked(timings):
        text = body.text.strip()
        timings.stt_chars = len(text)

        if not text:
            raise api_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ERR_EMPTY_TRANSCRIPTION,
                "El texto del comando esta vacio.",
            )

        return await _generate_response(
            user_text=text,
            house_context=_parse_house_context(body.house_context_json),
            voice=body.voice,
            timings=timings,
            background_tasks=background_tasks,
            llm_service=llm_service,
            tts_service=tts_service,
        )


async def _generate_response(
    user_text: str,
    house_context: HouseContext,
    voice: str | None,
    timings: PipelineTimings,
    background_tasks: BackgroundTasks,
    llm_service: LLMService,
    tts_service: TTSService,
) -> FileResponse:
    """
    Parte comun del pipeline: LLM -> TTS -> respuesta con headers.

    Args:
        user_text: texto del usuario ya transcrito.
        house_context: estado de la casa.
        voice: voz de Edge TTS opcional.
        timings: cronometro de la peticion (se completa aqui).
        background_tasks: para borrar el MP3 despues de enviarlo.
        llm_service, tts_service: servicios a usar.

    Returns:
        FileResponse con el MP3 y los headers de accion.
    """
    # LLM: clasificar intencion y generar respuesta
    try:
        with timings.stage("llm"):
            llm_response = llm_service.process_message(
                user_text=user_text,
                house_context=house_context,
            )
    except RuntimeError as error:
        logger.error(f"[DEBUG] Fallo en LLM: {error}")
        raise api_error_from(
            error, ERR_LLM,
            f"Error en procesamiento de lenguaje (LLM): {error}",
            probe_host=GROQ_HOST,
        )

    timings.intent = llm_response.intent
    timings.response_chars = len(llm_response.response_text or "")
    timings.set_usage({
        "prompt_tokens": llm_response.prompt_tokens,
        "completion_tokens": llm_response.completion_tokens,
        "total_tokens": llm_response.tokens_used,
        "cached_tokens": llm_response.cached_tokens,
    })

    # TTS: sintetizar la respuesta en audio
    try:
        with timings.stage("tts"):
            _, tts_audio_path = await tts_service.synthesize(
                TTSRequest(text=llm_response.response_text, voice=voice)
            )
    except RuntimeError as error:
        logger.error(f"[DEBUG] Fallo en TTS: {error}")
        raise api_error_from(
            error, ERR_TTS,
            f"Error en sintesis de voz (TTS): {error}",
            probe_host=EDGE_TTS_HOST,
        )

    background_tasks.add_task(_delete_file, tts_audio_path)

    timings.status = "ok"
    return FileResponse(
        path=tts_audio_path,
        media_type="audio/mpeg",
        filename="response.mp3",
        headers=_build_response_headers(llm_response),
    )


@router.post(
    "/morning-greeting",
    response_class=FileResponse,
    summary="Saludo matutino con el clima",
    description=(
        "Genera el saludo matutino de Mía con la info del clima actual de Bogotá. "
        "Unity llama a este endpoint al abrir la aplicación una vez por día. "
        "Devuelve el audio MP3 con el saludo dinámico de Mía."
    ),
)
async def morning_greeting(
    request: MorningGreetingRequest,
    background_tasks: BackgroundTasks,
    tts_service: TTSService = Depends(get_tts_service),
):
    """
    Genera el saludo matutino dinamico de Mía.
    
    Consulta el clima actual de Bogota en OpenWeatherMap,
    construye el texto del saludo con el nombre del usuario,
    la hora y el clima, y lo sintetiza con la voz de Mía.

    Unity reproduce primero el audio pregrabado de bienvenida
    y luego el audio que devuelve este endpoint, creando una
    experiencia de transicion entre la voz grabada y Mía.

    Args:
        request: MorningGreetingRequest con nombre del usuario y voz opcional.
        background_tasks: gestor de tareas en segundo plano de FastAPI
        tts_service: servicio TTS inyectado,

    Returns:
        FileResponse con el audio MP3 del saludo de Mía.

    Raise:
        HTTPException 503: si el TTS o el clima no estan disponibles.
    """
    # Construir el texto del saludo con el clima actual
    weather_client = OpenWeatherClient()
    routine_service = MorningRoutineService(weather_client=weather_client)

    greeting_text = routine_service.build_greeting_text(
        user_name=request.user_name,
    )

    # Sintetizar el saludo con la voz de Mía
    tts_request = TTSRequest(
        text=greeting_text,
        voice=request.voice,
    )

    try:
        # Sintetizar el saludo
        _, audio_path = await tts_service.synthesize(tts_request)
    except RuntimeError as error:
        raise api_error_from(error, ERR_TTS, f"Error en sintesis de voz (TTS): {error}",
                probe_host=EDGE_TTS_HOST)
    
    # Eliminar en segundo plano el audio del saludo generado por Mía
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