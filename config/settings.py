# config/settings.py
# =============================================================
# Módulo de configuracion centralizada del sistema.
#
# Responsabilidad: leer las variables del archivo .env una sola
# vez al iniciar el servidor y exponerlas como objetos tipados
# al resto de las capas del sistema.
#
# Patron de diseño: Singleton — existe una unica instancia de
# Settings compartida por todo el proyecto.
# =============================================================

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Cargar el archivo .env en las variables de entorno del proceso
# Debe ejecutarse antes de cualquier llamada a os.getenv()
load_dotenv()

@dataclass(frozen=True)
class ServerSettings:
    """
    Configuracion del servidor HTTP

    Agrupa host y puerto donde el servidor escuchara conexiones.
    frozen=True hace que la clase sea inmutable despues de crearse. La
    configuracion no debe cambiar en tiempo de ejecucion
    """
    host: str
    port: int

@dataclass(frozen=True)
class GroqSettings:
    """
    Configuracion de conexion al LLM de Groq

    Contiene las credenciales y parametros necesarios para 
    hacer las peticiones a la API de Groq
    """
    api_key: str
    model: str
    endpoint: str

@dataclass(frozen=True)
class WhisperSettings:
    """
    Configuracion del modelo de Speech-to-Text Whisper.

    Define que tamanio de modelo cargar al iniciar el servidor.
    """
    model: str

@dataclass(frozen=True)
class TTSSettings:
    """
    Configuracion del motor de Text-to-Speech

    Define los valores por defecto de voz, velocidad y tono.
    Unity podra sobreescribir estos valores en cada peticion
    """
    default_voice: str
    default_speed: str
    default_pitch: str

@dataclass(frozen=True)
class AssistantSettings:
    """
    Configuracion general del asistente del hogar

    Contiene parametros de identidad y comportamineto del asistente
    """
    name: str


# CLASE PRINCIPAL QUE UNIRA TODOS LOS GRUPOS ANTERIORES Y TENDRA EL SINGLETON
@dataclass(frozen=True)
class Settings:
    """
    Configuracion global del sistema del asistente de la casa.

    Agrega todos los grupos de configuracion en un unico objeto.
    Se instancia una sola vez al cargar el modulo (patron Singleton)
    y se comparte por todas las capas del sistema.

    Uso:
        from config.settings import settings
        print(settings.assistant.name)
        print(settings.groq.api_key)
    """
    server: ServerSettings
    groq: GroqSettings
    whisper: WhisperSettings
    tts: TTSSettings
    assistant: AssistantSettings

def _load_settings() -> Settings:
    """
    Lee las variables de entorno y construye el objeto Settings.

    Valida que las variables criticas esten presentes antes de
    continuar. Si falta alguna variable obligatoria, lanza un
    error descriptivo para que desde desarrollo se sepa
    exactamente que falta configurar.

    Returns:
        Settings: Objeto con toda la configuracion del sistema.
    Raises:
        ValueError: Si falta alguna variable de entorno obligatoria.
    """
    _validate_required_env_vars()

    return Settings(
        server=ServerSettings(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8000")),
        ),
        groq=GroqSettings(
            api_key=os.getenv("GROQ_API_KEY"),
            model=os.getenv("GROQ_MODEL"),
            endpoint=os.getenv("GROQ_ENDPOINT"),
        ),
        whisper=WhisperSettings(
            model=os.getenv("WHISPER_MODEL", "base")
        ),
        tts=TTSSettings(
            default_voice=os.getenv("TTS_DEFAULT_VOICE", "es-CL-CatalinaNeural"),
            default_speed=os.getenv("TTS_DEFAULT_SPEED", "+0%"),
            default_pitch=os.getenv("TTS_DEFAULT_PITCH", "+0Hz"),
        ),
        assistant=AssistantSettings(
            name=os.getenv("ASSISTANT_NAME", "ARIA")
        ),
    )

def _validate_required_env_vars() -> None:
    """
    Valida que las variables de entorno obligatorias esten definidas

    Las variables con valores por defecto no son obligatorias.
    Las variables sin valor por defecto si lo son. El sistema
    no puede funcionar sin ellas.
    
    Raises:
        ValueError: Si falta alguna variable de entorno obligatoria.
    """

    # Variables que no tienen valor por defecto y son criticas
    required_vars = [
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "GROQ_ENDPOINT",
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        raise ValueError(
            f"Faltan las siguientes variables de entorno obligatorias: "
            f"{', '.join(missing_vars)}. "
            f"Verifica tu archivo .env."
        )
    
# =============================================================
# Instancia Singleton — se crea una vez al importar el modulo.
# Todas las capas del sistema importan esta instancia.
#
# Uso correcto:
#   from config.settings import settings
#
# Nunca instanciar Settings() directamente en otro modulo.
# =============================================================
settings = _load_settings()