# services/tts_service.py
# =============================================================
# Servicio de síntesis de voz del asistente del hogar.
#
# Responsabilidad: orquestar la generacion de audio coordinando
# la configuracion del sistema, los modelos de datos y el
# cliente de infraestructura TTS. Contiene la logica de negocio
# de la síntesis de voz sin acoplarse a ningun motor especifico.
#
# Patron: Dependency Injection — recibe el cliente TTS como
# dependencia en lugar de crearlo internamente.

# Principio D de SOLID — depende de BaseTTSClient (abstracción),
# no de EdgeTTSClient (implementación concreta).
# =============================================================

import os
import uuid
from infrastructure.tts.base_tts_client import BaseTTSClient
from models.tts_request import TTSRequest
from models.tts_response import TTSResponse
from config.settings import settings

# Directorio donde se guardan los archivos de audio temporales
# Relativo a la raiz del proyecto
TEMP_AUDIO_DIR = "temp_audio"

# Formato de los archivos de audio generados
AUDIO_FILE_EXTENSION = ".mp3"

class TTSService:
    """
    Servicio de logica de negocio para sintesis de voz.
    
    Orquesta la generacion de audio usando el cliente TTS
    inyectado. No conoce los detalles de ningun motor TTS
    especifico, solo conoce el contrato BaseTTSClient.

    Patron aplicado: Dependency Injection
    El cliente TTS se inyecta en el constructor, permitiendo
    cambiar el motor sin modificar esta clase.

    Attributes:
        _tts_cliente: cliente TTS que implementa BaseTTSClient.
    """

    def __init__(self, tts_client: BaseTTSClient) -> None:
        """
        Inicializa el servicio con el ciente TTS inyectado

        Args:
            tts_client: Implementacion de BaseTTSClient a usar.
                Puede ser EdgeTTSClient, KokoroTTSClient, etc.
        """
        self._tts_client = tts_client

    async def synthesize(self, request: TTSRequest) -> tuple[TTSResponse, str]:
        """
        Genera audio a partir de una peticion de sintesis de voz.
        
        Resuelve los parametros de voz (usando defaults del .env
        cuando Unity no los especifica), delega la generacion al
        cliente de infraestructura y construye la respuesta.

        Args:
            request: TTSRequest con el texto y parametros opcionales.

        Returns:
            Tupla de TTSResponse con metadatos, str con la ruta 
            del archivo de audio generado.

        Raises:
            RuntimeError: si el cliente TTS falla al generar audio.
        """
        # Resolver parametros. Usar los de la peticion si vienen,
        # si no, usar los valores por defecto del .env
        voice = self._resolve_voice(request.voice)
        speed = self._resolve_speed(request.speed)
        pitch = self._resolve_pitch(request.pitch)

        # Generar ruta unica para este archivo de audio
        output_path = self._build_output_path()

        try:
            await self._tts_client.generate_audio(
                text=request.text,
                voice=voice,
                speed=speed,
                pitch=pitch,
                output_path=output_path,
            )
        except Exception as error:
            raise RuntimeError(
                f"Error al generar audio con el motor TTS correspondiente "
                f"'{self._tts_client.get_engine_name()}': {error}"
            ) from error
        
        response = TTSResponse(
            success=True,
            message="Audio generado correctamente.",
            voice_used=voice,
            audio_duration_ms=None, # Se calculara en un paso a futuro
        )

        return response, output_path
    
    def get_available_voices(self) -> list[str]:
        """
        Retorna las voces disponibles en el motor TTS activo.

        Delega directamente al cliente de infraestructura.
        Permite que la capa API exponga las voces disponibles
        a Unity para su selector de voces.

        Returns:
            Lista de identificadores de voces disponibles.
        """
        return self._tts_client.get_availables_voices()
    
    def get_active_engine(self) -> str:
        """
        Retorna el nombre del motor TTS que se estaria usando
        
        Se puede usar para logging y para informar a Unity que motor
        esta usandose.

        Returns:
            Nombre del motor. Ej: 'edge_tts', 'kokoro'.
        """
        return self._tts_client.get_engine_name()
    
    def _resolve_voice(self, requested_voice: str | None) -> str:
        """
        Resuelve que voz usar para la sintesis de voz.

        Si Unity envio una voz especifica, la usa. Si no,
        usa el valor por defecto configurado en el .env.
        
        Args:
            requested_voice: voz solicitada por Unity o None.

        Returns:
            Identificador de voz a usar.
        """
        return requested_voice or settings.tts.default_voice
    
    def _resolve_speed(self, requested_speed: str | None) -> str:
        """
        Resuelve que velocidad usar para la sintesis de voz.

        Args:
            requested_speed: velocidad solicitada o None si se
            dejara la establecida por defecto.

        Returns:
            Velocidad a usar en formato Edge TTS. Ej: '+0%'.
        """
        return requested_speed or settings.tts.default_speed

    def _resolve_pitch(self, requested_pitch: str | None) -> str:
        """
        Resuelve que tono usar para la sintesis de voz.
        
        Args:
            requested_pitch: tono solicitado o None para usar el pitch
            por defecto

        Returns:
            Tono a usar en formato Edge TTS. Ej: '+0Hz'.
        """
        return requested_pitch or settings.tts.default_pitch
    
    def _build_output_path(self) -> str:
        """
        Construye una ruta unica para el archivo de audio temporal.

        Usa UUID para garantizar que cada archivo tenga un
        nombre unico, evitando conflictos cuando multiples 
        peticiones lleguen al mismo tiempo.

        Returns:
            Ruta completa del archivo. Ej:
            'temp_audio/a3f1c2d4-...-9b8e.mp3'
        """
        unique_filename = f"{uuid.uuid4()}{AUDIO_FILE_EXTENSION}"
        return os.path.join(TEMP_AUDIO_DIR, unique_filename)