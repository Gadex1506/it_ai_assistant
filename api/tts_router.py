# api/tts_router.py
# =============================================================
# Router HTTP para el sistema de sintesis de voz.
#
# Responsabilidad: definir y manejar los endpoints HTTP del
# subsistema TTS. Recibe peticiones de Unity, las delega al
# servicio de logica de negocio y devuelve las respuestas.
#
# Patron: Factory Method — funcion `get_tts_service()` construye
# el TTSService con sus dependencias correctamente inyectadas.

# Principio S de SOLID — este modulo solo maneja HTTP para TTS.
# No contiene logica de negocio ni conoce motores TTS.
# =============================================================

import os
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import FileResponse

from models.tts_request import TTSRequest
from models.tts_response import TTSResponse
from services.tts_service import TTSService
from infrastructure.tts.edge_tts_client import EdgeTTSClient

# Informacion de tipo de posibles errores del servidor
from api.error_codes import api_error_from, ERR_TTS, EDGE_TTS_HOST

# Prefijo de todas las rutas de este router
# Todos los endpoints quedan bajo /tts/
ROUTER_PREFIX = "/tts"
ROUTER_TAG = "Text-to-Speech"

# =============================================================
# Factory Method — construye TTSService con sus dependencias.
# FastAPI llama a esta funcion automaticamente cada vez que
# un endpoint la declara como dependencia con Depends().
# =============================================================

def get_tts_service() -> TTSService:
    """
    Factory que construye y retorna una instancia de TTSService.
    
    Centraliza la creacion del servicio con su cliente TTS
    inyectado. Si en el futuro se cambia el motor TTS,
    solo se modifica esta funcion. Ningun endpoint cambia.

    Returns:
        TTSService configurado con EdgeTTSClient.
    """
    return TTSService(tts_client=EdgeTTSClient())

# Instancia del router. Agrupa todos los endpoints TTS
router = APIRouter(prefix=ROUTER_PREFIX, tags=[ROUTER_TAG])

# =============================================================
# Endpoints
# =============================================================

@router.post(
    "/speak",
    response_class=FileResponse,
    summary="Sintetizar texto a voz",
    description=(
        "Recibe texto desde Unity y devuelve un archivo de audio .mp3 "
        "generado con el motor TTS configurado. "
        "Si no se específica voz, usa la voz por defecto del servidor."
    ),
)
async def speak(
    request: TTSRequest,
    background_tasks: BackgroundTasks,
    service: TTSService = Depends(get_tts_service),
):
    """
    Endpoint principal de sintesis de voz
    
    Recibe una TTSRequest con el texto y parametros opcionales de voz,
    genera el audio y lo devuelve como archivo .mp3.
    Ademas, programa la eliminacion automatica de
    los archivos .mp3 de forma automatica en
    segundo plano.

    Args:
        request: TTSRequest con texto y parametros de voz.
        background_tasks: gestor de tareas en segundo plano de FastAPI.
        service: TTSService inyectado por FastAPI via Depends().

    Returns:
        FileResponse con el archivo .mp3 generado.

    Raises:
        HTTPException 503: si el motor TTS falla al generar audio.
        HTTPException 500: si el archivo no se encuentra tras generarse.
    """
    try:
        response_metadata, audio_path = await service.synthesize(request)
    except RuntimeError as error:
        raise api_error_from(error, ERR_TTS, f"Error en sintesis de voz: {error}",
                    probe_host=EDGE_TTS_HOST)
    
    # Verificar que el archivo fue realmente creado
    if not os.path.exists(audio_path):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El audio fue procesado pero el archivo no se encontro.",
        )
    
    background_tasks.add_task(_delete_audio_file, audio_path)

    # FileResponse envia el archivo directamente como respuesta HTTP.
    # background elimina el archivo temporal despues de enviarlo
    # para no acumular .mp3 en temp_audio/
    return FileResponse(
        path=audio_path,
        media_type="audio/mpeg",
        filename="response.mp3",
        headers={
            "X-Voice-Used": response_metadata.voice_used,
            "X-engine": service.get_active_engine(),
        },
    )

def _delete_audio_file(file_path: str) -> None:
    """
    Elimina un archivo de audio temporal del disco.
    
    Se ejecuta como BackgroundTask despues de que FastAPI
    termina de enviar el archivo al cliente (Unity). Asi Unity
    recibe el audio completo antes de que se elimine.
    
    Args:
        file_path: ruta completa del archivo .mp3 a elimnar.

    Returns:
        None.
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError as error:
        # No relanzamos el error, es una tarea de limpieza,
        # en teoria, no deberia de afectar la respuesta ya enviada a Unity.
        print(f"Advertencia: no se pudo eliminar {file_path}: {error}")

@router.get(
    "/voices",
    response_model=dict,
    summary="Listar voces disponibles",
    description=(
        "Retorna la lista de voces disponibles en el motor TTS activo. "
        "Unity usa este endpoint para llenar el selector de voces."
    ),
)
def get_voices(
    service: TTSService = Depends(get_tts_service),
):
    """
    Endpoint que retorna las voces disponibles en el motor TTS seleccionado.
    
    Permite que Unity consulte dinamicamente que voces puede
    seleccionar sin harcodear la lista en el cliente.

    Args:
        service: TTSService inyectado por FastAPI via Depends().
    Returns:
        Dict con el nombre del motor y lista de voces disponibles en ese motor TTS.
    """
    return {
        "engine": service.get_active_engine(),
        "voices": service.get_available_voices(),
        "total": len(service.get_available_voices()),
    }

@router.get(
    "/health",
    summary="Estado del servicio TTS",
    description="Verifica que el servicio TTS está funcionando."
)
def health_check(
    service: TTSService = Depends(get_tts_service),
):
    """
    Endpoint de salud del servicio TTS.
    
    Unity puede llamar este endpoint antes de enviar peticiones
    para verificar que el servidor TTS esta disponible.

    Args:
        service: TTSService inyectado por FastAPI via Depends().

    Returns:
        Dict con estado del servicio y motor activo.
    """
    return {
        "status": "ok",
        "engine": service.get_active_engine(),
        "voices_available": len(service.get_available_voices()),
    }