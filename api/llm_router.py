# api/llm_router.py
# =============================================================
# Router HTTP para el sistema de procesamiento de lenguaje natural.
#
# Responsabilidad: definir y manejar los endpoints HTTP del
# subsistema LLM. Recibe texto y contexto del hogar desde Unity,
# los delega al servicio de logica de negocio y devuelve la
# respuesta con la intencion clasificada y la accion a ejecutar.
#
# Patron: Factory Method - funcion get_llm_service() construye
# el LLMService con sus dependencias correctamente inyectadas.
#
# Principio S de SOLID - este modulo solo maneja HTTP para LLM.
# No contiene logica de negocio ni conoce proveedores LLM.
# =============================================================
    
from fastapi import APIRouter, Depends , HTTPException, Request, status
from models.llm_request import LLMRequest, HouseContext
from models.llm_response import LLMResponse
from services.llm_service import LLMService


ROUTER_PREFIX = "/llm"
ROUTER_TAG = "Language Model"


# =============================================================
# Factory Method - construye LLMService con sus dependencias.
# Lee el cliente LLM precargado desde app.state, siguiendo
# el mismo patron establecido en el router STT.
# =============================================================
def get_llm_service(request: Request) -> LLMService:
    """
    Factory que retorna LLMService usando el cliente LLM
    precargado en app.state durante el startup del servidor.

    Args:
        request: peticion HTTP actual. FastAPI la inyecta
            automaticamente para acceder a app.state.

    Returns:
        LLMService configurado con cliente precargado.
    """
    return request.app.state.llm_service

router = APIRouter(prefix=ROUTER_PREFIX, tags=[ROUTER_TAG])


# =============================================================
# Endpoints
# =============================================================

@router.post(
    "/chat",
    response_model=LLMResponse,
    summary="Procesar mensaje del usuario",
    description=(
        "Recibe el texto transcrito por el STT del usuario y el estado actual "
        "de la casa desde Unity. Clasifica la intencion del comando dicho por el usuario, "
        "genera la respuesta en texto y extrae el comando de accion si corresponde. "
        "Todo en una sola llamada al LLM."
    ),
)
def chat(
    request: LLMRequest,
    service: LLMService = Depends(get_llm_service),
):
    """
    Endpoint principal del susbsitema LLM.
    
    Recibe un LLMRequest con el texto del usuario y el contexto
    del hogar, procesa el mensaje con el LLM y devuelve un
    LLMResponse con la intencion, la respuesta en texto y
    la accion del hogar si corresponde.

    Unity usa este endpoint para obtener:
    1. El texto que ARIA dira en voz alta para despues enviarlo al TTS.
    2. La accion a ejecutar en la casa si aplica.

    Args:
        request: LLMRequest con texto del usuario y contexto del hogar.
        service: LLMService inyectado por FastAPI via Depends().

    Returns:
        LLMResponse con intent, response_text y action opcional.
    
    Raise:
        HTTException 503: si el proveedor LLM no esta disponible.
    """
    try:
        response = service.process_message(
            user_text=request.user_text,
            house_context=request.house_context,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error al procesar el mensaje: {error}",
        )
    
    return response

@router.post(
    "/clear-history",
    summary="Limpiar historial de conversacion",
    description=(
        "Limpia el historial de conversacion de la sesion actual. "
        "Unity llama a este endpoint cuando el usuario termina "
        "una sesion para empezar una nueva sin contexto previo."
    ),
)
def clear_history(
    service: LLMService = Depends(get_llm_service),
):
    """
    Limpia el historial de conversacion del asistente.
    
    Args:
        service: LLMService inyectado por FastAPI via Depends().

    Returns:
        Dict confirmando que el historial fue limpiado.
    """
    service.clear_conversation_history()

    return {
        "status": "ok",
        "message": "Historial de conversacion limpiado correctamente.",
    }

@router.get(
    "/health",
    summary="Estado del servicio LLM",
    description="Verifica que el servicio LLM esta operativo.",
)
def health_dehck(
    service: LLMService = Depends(get_llm_service)
):
    """
    Endpoint de salud del servicio LLM.

    Args:
        service: LLMService inyectado por FastAPI via Depends().

    Returns:
        Dict con estado del servicio, proveedor y modelo activos.
    """
    return {
        "status": "ok",
        "provider": service.get_active_provider(),
        "model": service.get_active_model(),
    }