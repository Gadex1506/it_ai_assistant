# api/error_codes.py
# =============================================================
# Codigos de error compartidos por todos los routers.
#
# Responsabilidad: definir los codigos que el cliente (Unity) entiende
# (header X-Error-Code) y decidir cual corresponde a cada falla.
# Ningun router repite esta logica.
# =============================================================

import socket

from fastapi import HTTPException, status

# Header con el codigo de error. El cliente (Unity) lo lee para mostrar el mensaje correcto.
ERROR_CODE_HEADER = "X-Error-Code"

ERR_EMPTY_TRANSCRIPTION = "empty_transcription"
ERR_STT = "stt_error"
ERR_NO_INTERNET = "no_internet"
ERR_RATE_LIMITED = "rate_limited"
ERR_LLM = "llm_error"
ERR_TTS = "tts_error"

# Se comparan nombres de clase para no depender de un SDK concreto
_NETWORK_ERROR_NAMES = {
    "APIConnectionError", "APITimeoutError", "ConnectError", "ConnectTimeout",
    "ReadTimeout", "TimeoutException", "ClientConnectorError",
    "ClientConnectionError", "ServerTimeoutError", "ServerDisconnectedError",
    "ClientOSError", "ConnectionError", "TimeoutError", "gaierror",
}
_RATE_LIMIT_ERROR_NAMES = {"RateLimitError"}

# Respaldo cuando la excepcion original se perdio y solo queda el texto
_NETWORK_MESSAGE_HINTS = (
    "connect", "timed out", "timeout", "getaddrinfo",
    "name resolution", "name or service not known", "network",
)

# Servidores que se comprueban cuando una falla no tiene causa reconocible
GROQ_HOST = "api.groq.com"
EDGE_TTS_HOST = "speech.platform.bing.com"
_PROBE_PORT = 443
_PROBE_TIMEOUT_SECONDS = 1.5

def _host_reachable(host: str) -> bool:
    """
    Comprueba si se puede abrir una conexion con el servidor del proveedor.

    Solo se usa cuando una falla ya ocurrio, para distinguir "no hay
    internet" de "el proveedor respondio con un error".

    Args:
        host: nombre del servidor a comprobar.

    Returns:
        True si la conexion se abrio, False si fallo (sin red, DNS, etc.).
    """
    try:
        with socket.create_connection((host, _PROBE_PORT), timeout=_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False

def api_error(status_code: int, code: str, detail: str) -> HTTPException:
    """
    Construye un HTTPException que lleva el codigo de error en un header.

    Args:
        status_code: codigo HTTP de la respuesta.
        code: codigo interno (ERR_*) que Unity traduce a un mensaje.
        detail: texto tecnico para logs y para /docs.

    Returns:
        HTTPException listo para lanzar con raise.
    """
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={ERROR_CODE_HEADER: code},
    )


def classify_error(error: Exception, default_code: str, probe_host: str | None = None) -> str:
    """
    Decide si una falla fue por red, por limite de uso u otra causa.

    Recorre la cadena de excepciones (__cause__ / __context__) buscando
    el error original del SDK y, como respaldo, revisa el texto del mensaje.

    Args:
        error: excepcion capturada.
        default_code: codigo a usar si no es ni red ni limite de uso.

    Returns:
        ERR_RATE_LIMITED, ERR_NO_INTERNET o default_code.
    """
    current = error
    for _ in range(5):
        name = type(current).__name__
        if name in _RATE_LIMIT_ERROR_NAMES:
            return ERR_RATE_LIMITED
        if name in _NETWORK_ERROR_NAMES:
            return ERR_NO_INTERNET
        current = current.__cause__ or current.__context__
        if current is None:
            break

    message = str(error).lower()
    if "rate limit" in message or "429" in message:
        return ERR_RATE_LIMITED
    if any(hint in message for hint in _NETWORK_MESSAGE_HINTS):
        return ERR_NO_INTERNET
    if probe_host and not _host_reachable(probe_host):
        return ERR_NO_INTERNET
    return default_code


def api_error_from(error: Exception, default_code: str, detail: str, probe_host: str | None = None) -> HTTPException:
    """
    Clasifica una excepcion y devuelve el HTTPException correspondiente.

    Args:
        error: excepcion capturada.
        default_code: codigo si no es red ni limite de uso.
        detail: texto tecnico de la respuesta.

    Returns:
        HTTPException con el status y el header de error adecuados.
    """
    code = classify_error(error, default_code, probe_host)
    http_status = (
        status.HTTP_429_TOO_MANY_REQUESTS
        if code == ERR_RATE_LIMITED
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return api_error(http_status, code, detail)

def error_code_of(exc: HTTPException) -> str:
    """Devuelve el codigo de error de un HTTPException, o http_<status> si no tiene."""
    headers = exc.headers or {}
    return headers.get(ERROR_CODE_HEADER, f"http_{exc.status_code}")