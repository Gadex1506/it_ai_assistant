# api/stt_router.py
# =============================================================
# Router HTTP para el sistema de reconocimiento de voz.
#
# Responsabilidad: definir y manejar los endpoints HTTP del
# subsistema STT. Recibe archivos de audio del cliente (Unity), los
# delega al servicio de logica de negocio y devuelve el
# texto transcrito como JSON.
#
# Patron Factory Method: funcion get_stt_service() construye
# el STTService con sus dependencias correctamente inyectadas.

# Principio S de SOLID: este modulo solo maneja HTTP para STT.
# No contiene logica de negocio ni conoce motores STT.
# =============================================================

import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from models.stt_result import STTResult
from services.stt_service import STTService

ROUTER_PREFIX = "/stt"
ROUTER_TAG = "Speech-to-Text"

# Tamanio maximo permitido para archivos de audio entrantes (en bytes)
# 10 MB es suficiente para capturas de voz hasta varios minutos.
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024

# Formatos de audio aceptados desde Unity
ACCEPTED_AUDIO_FORMATS = {".wav", ".mp3", ".ogg", ".m4a"}

# =============================================================
# Factory Method — construye STTService con sus dependencias.
# FasterWhisperClient se instancia una sola vez gracias a que
# FastAPI cachea las dependencias marcadas con use_cache=True.
# =============================================================

def get_stt_service(request: Request) -> STTService:
    """
    Factory que retorna STTService usando el cliente STT
    precargado en app.state durante el startup del servidor.

    Reutilizar la misma instancia de FasterWhisperClient
    evita recargar el modelo Whisper en cada peticion.

    Args:
        request: peticion HTTP actual. FastAPI la inyecta
                automaticamente para acceder a app.state.

    Returns:
        STTService configurado con el cliente precargado.
    """
    return STTService(stt_client=request.app.state.stt_client)

router = APIRouter(prefix=ROUTER_PREFIX, tags=[ROUTER_TAG])

# =============================================================
# Endpoints
# =============================================================

@router.post(
    "/transcribe",
    response_model=STTResult,
    summary="Transcribir audio a texto",
    description=(
        "Recibe un archivo de audio desde el cliente (Unity) y devuelve el texto "
        "transcrito usando Faster Whisper. Detecta el idioma "
        "automáticamente si no se específica."
    ),
)
async def transcribe(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(
        ...,
        description="Archivo de audio a transcribir. Formatos: .wav, .mp3, .ogg, .m4a",
    ),
    language: str | None = None,
    service: STTService = Depends(get_stt_service),
):
    """
    Endpoint principal de transcripcion de voz.

    Recibe un archivo de audio del cliente (Unity) via multipart/form-data,
    lo transcribe con Whisper y devuelve el STTResult como JSON.
    El archivo temporal se elimina en segundo plano despues de que este servidor
    le responde al cliente (Unity).
    
    Args:
        background_tasks: gestor de tareas en segundo plano de FastAPI.
        audio_file: archivo de audio enviado por el cliente (Unity).
        language: codigo de idioma opcional. Ejemplo: 'es', 'en'.
            Si no se envia, Whisper detecta el idioma automaticamente.
        service: STTService inyectado por FastAPI via Depends().

    Returns:
        STTResult con texto transcrito, idioma, confianza y tiempo.

    Raises:
        HTTPException 400: si el formato del archivo no es soportado
            o el archivo supera el tamanio maximo.
        HTTPException 503: si Whisper falla al transcribir.
    """
    _validate_audio_format(audio_file.filename)

    audio_bytes = await audio_file.read()

    _validate_audio_size(audio_bytes)

    try:
        result, audio_path = service.transcribe_audio(
            audio_bytes=audio_bytes,
            language=language,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error en transcripcion de voz: {error}",
        )
    
    background_tasks.add_task(_delete_audio_file, audio_path)

    return result

@router.get(
    "/languages",
    summary="Listar idiomas soportados por el motor STT activo",
    description=(
        "Retorna la lista de idiomas que el motor STT activo "
        "puede trasncribir. El cliente (Unity) usa este endpoint para "
        "mostrar las opciones de idioma disponibles."
    ),
)
def get_Languages(
    service: STTService = Depends(get_stt_service),
):
    """
    Endpoint que retorna los idiomas soportados por el motor STT.
    
    Args:
        service: STTService inyectado por FastAPI via Depends().

    Returns:
        Dict con el motor activo y lista de idiomas soportados.
    """
    return {
        "engine": service.get_active_engine(),
        "languages": service.get_supported_languages(),
        "total": len(service.get_supported_languages()),
        "auto-detect": True,
    }

@router.get(
    "/health",
    summary="Estado del servicio STT",
    description="Verifica que el servicio STT está funcionando.",
)
def health_check(
    service: STTService = Depends(get_stt_service),
):
    """
    Endpoint de salud del servicio STT.
    
    Args:
        service: STTService inyectado por FastAPI via Depends().

    Returns:
        Dict con estado del servicio y motor activo.
    """
    return {
        "status": "ok",
        "engine": service.get_active_engine(),
        "languages_availables": len(service.get_supported_languages()),
        "auto-detect_languages": True,
    }

# =============================================================
# Funciones de soporte
# =============================================================

def _validate_audio_format(filename: str | None) -> None:
    """
    Valida que el archivo de audio tiene un formato soportado.
    
    Args:
        filename: nombre del archivo enviado por el cliente (Unity).

    Raises:
        HTTPException 400: si el formato no esta en la lista
            de formatos aceptados.
    """
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo de audio no tiene nombre. "
                    "Verifica que Unity esta enviando el archivo correctamente.",
        )
    
    file_extension = os.path.splitext(filename)[1].lower()

    if file_extension not in ACCEPTED_AUDIO_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de audio no soportado: '{file_extension}'. "
                    f"Formatos aceptados: {', '.join(ACCEPTED_AUDIO_FORMATS)}.",
        )
    
def _validate_audio_size(audio_bytes: bytes) -> None:
    """
    Valida que el archivo de audio no exceda el tamanio maximo permitido.
    
    Args:
        audio_bytes: bytes del archivo de audio recibido.

    Raises:
        HTTPException 400: si el archivo super MAX_AUDIO_SIZE_BYTES.
    """
    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        max_mb = MAX_AUDIO_SIZE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo de audio supera el tamanio maximo "
                    f"permitido de {max_mb} MB.",
        )
    
def _delete_audio_file(file_path: str) -> None:
    """
    Elimna un archivo de audio temporal del disco.
    
    Se ejecuta como BackgroundTask (Tarea Secundaria) despues de
    que FastAPI termina de enviar la respuesta al cliente.

    Args:
        file_path: ruta completa del archivo a eliminar.

    Returns:
        None.
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError as error:
        print(f"Advertencia: no se pudo eliminar {file_path}: {error}")