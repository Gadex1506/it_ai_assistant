# main.py
# =============================================================
# Punto de entrada del servidor del asistente del hogar.
#
# Responsabilidad: inicializar la aplicacion FastAPI, crear
# los clientes de infraestructura una sola vez al arrancar,
# registrar todos los routers y gestionar el ciclo de vida
# completo del servidor.
#
# Patron: Observer: eventos startup/shutdown de FastAPI notificaran
# al sistema para inicializar el servidor y limpiar recursos al finalizar su ejecucion.
# Patron: Singleton para los clientes de infraestructura
# pesados como FasterWhisperClient que se crean una sola vez.
# =============================================================

import os
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Global Settings
from config.settings import settings

# Services
from services.llm_service import LLMService

# Routers
from api.stt_router import router as stt_router
from api.llm_router import router as llm_router
from api.tts_router import router as tts_router
from api.assistant_router import router as assistant_router

# Infrastruture
from infrastructure.stt.faster_whisper_client import FasterWhisperClient
from infrastructure.llm.groq_client import GroqClient


# =============================================================
# Configuracion del logger del sistema
# Permite rastrear el comportamiento del servidor en consola
# =============================================================

logger = logging.getLogger("it_ai_assistant")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.propagate = False

# Directorio de archivos de audio temporales
TEMP_AUDIO_DIR = "temp_audio"

# =============================================================
# Ciclo de vida del servidor: Patron Observer
# asynccontextmanager define que pasa al arrancar antes del yield,
# y que pasa al apagar despues del yield
# =============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida completo del servidor.

    Startup: crea directorios necesarios y registra el inicio del servidor
    Shutdown: limpia recursos y registra cierre ordenado del servidor

    Args:
        app: instancia de FastAPI
    """

    # ── STARTUP ──────────────────────────────────────────────
    logger.info("=" * 50)
    logger.info(f"Iniciando {settings.assistant.name} Assistant Server")
    logger.info(f"Host: {settings.server.host}:{settings.server.port}")
    logger.info("=" * 50)

    # Crear directorio de audio temporal si no existe
    _ensure_temp_audio_directory()
    logger.info(f"Directorio temporal listo: {TEMP_AUDIO_DIR}/")

    # ====== CARGA DEL STT WHISPER ======
    # Crear FasterWhisperClient una sola vez y guardarlo en
    # app.state para reutilizarlo en todas las peticiones.
    # Esto evita recargar el modelo en cada llamada del endpoint
    logger.info(f"Cargando modelo Whisper '{settings.whisper.model}'...")
    app.state.stt_client = FasterWhisperClient()
    logger.info("Modelo Whisper para STT cargado y listo.")

    # ====== CARGA DEL LLM ======
    logger.info("Inicializando servicio LLM con Groq...")
    app.state.llm_service = LLMService(llm_client=GroqClient())
    logger.info("Servicio LLM listo.")

    logger.info("Servidor listo para recibir peticiones.")

    yield # El servidor corre aqui

    # ── SHUTDOWN ─────────────────────────────────────────────
    logger.info(f"Apagando servidor {settings.assistant.name} Assistant Server...")
    _cleanup_temp_audio_directory()
    logger.info("Archivos temporales eliminados")
    logger.info("Servidor apagado correctamente.")

# =============================================================
# Inicializacion de la aplicacion FastAPI
# =============================================================
app = FastAPI(
    title=f"{settings.assistant.name} - Servidor del Asistente del Hogar",
    description=(
        "API del asistente de voz inteligente para el sistema domotico de Inclusive Tech. "
        "Provee sintesis de voz (TTS), transcripcion de audio (STT) "
        "y procesamiento de lenguaje natural (LLM)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# =============================================================
# Registro de routers
# Cada modulo registra aqui sus endpoints (STT, LLM y TTS)
# =============================================================

app.include_router(tts_router)
app.include_router(stt_router)
app.include_router(llm_router)
app.include_router(assistant_router)

# =============================================================
# Manejador global de errores no controlados
# Captura cualquier excepcion que no fue manejada en los
# routers y devuelve una respuesta JSON consistente
# en lugar de un error 500 generico de FastAPI
# =============================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, error: Exception):
    """
    Maneja excepciones no controladas del servidor.

    Registra el error en el log y devuelve una respuesta
    JSON con mensaje descriptivo en lugar de un error 500
    generico de FastAPI.
    
    Args:
        request: peticion HTTP que causo el error.
        error: excpecion no controlada.

    Returns:
        JSONResponse: con codigo 500 y detalle del error.
    """
    logger.error(
        f"Error no controlado en {request.method} {request.url}: {error}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Error interno del servidor.",
            "detail": str(error),
            "path": str(request.url),
        },
    )

# =============================================================
# Endpoint raiz
# =============================================================
@app.get("/", tags=["General"])
def root():
    """
    Endpoint raiz. Confirma que el servidor se encuentra en linea
    
    Returns:
        Dict con estado del servidor y nombre del asistente
    """
    return {
        "status": "online",
        "assistant": settings.assistant.name,
        "version": "1.0.0",
        "docs": "/docs",
    }

# =============================================================
# Funciones de soporte del ciclo de vida
# =============================================================
def _ensure_temp_audio_directory() -> None:
    """
    Crea el directorio de audio temporal si no existe.
    
    Returns:
        None.
    """
    if not os.path.exists(TEMP_AUDIO_DIR):
        os.makedirs(TEMP_AUDIO_DIR)
        logger.info(f"Directorio creado: {TEMP_AUDIO_DIR}/")

def _cleanup_temp_audio_directory() -> None:
    """
    Elimina todos los archivos .mp3 y .wav del directorio temporal.
    
    Se ejecuta al apagar el servidor para liberar espacio.
    Solo elimina archivos, no elimina el directorio.

    Returns:
        None.
    """
    if not os.path.exists(TEMP_AUDIO_DIR):
        return
    
    deleted_count = 0
    for filename in os.listdir(TEMP_AUDIO_DIR):
        if filename.endswith((".mp3", ".wav")):
            file_path = os.path.join(TEMP_AUDIO_DIR, filename)
            try:
                os.remove(file_path)
                deleted_count += 1
            except OSError as error:
                logger.warning(
                    f"No se pudo eliminar {file_path}: {error}"
                )

    if deleted_count > 0:
        logger.info(f"{deleted_count} archivos(s) temporal(es) eliminado(s).")

# =============================================================
# Punto de entrada
# =============================================================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
    )