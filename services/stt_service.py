# services/stt_service.py
# =============================================================
# Servicio de reconocimiento de voz del asistente del hogar.
#
# Responsabilidad: orquestar la transcripcion de audio
# coordinando el almacenamiento temporal del archivo de audio,
# el cliente de infraestructura STT y la construccion de la
# respuesta para la capa de presentacion.
#
# Patron: Dependency Injection — recibe el cliente STT como
# dependencia en lugar de crearlo internamente.

# Principio D de SOLID — depende de BaseSTTClient (abstraccion),
# no de FasterWhisperClient (implementacion concreta).
# =============================================================

import os
import uuid
from infrastructure.stt.base_stt_client import BaseSTTClient
from models.stt_result import STTResult

# Directorio donde se guardan los archivos de audio temporales
# recibidos desde el cliente (Unity) para ser procesados por Whisper.
TEMP_AUDIO_DIR = "temp_audio"

# Extension del archivo de audio que Unity enviara al servidor.
# Unity graba en formato WAV por compatibilidad con Whisper.
AUDIO_FILE_EXTENSION = ".wav"

class STTService:
    """
    Servicio de logica de negocio para el reconocimiento de voz (STT).
    
    Orquesta la transcripcion de audio usando el cliente STT
    inyectado. Gestiona el ciclo de vida de los archivos de
    audio temporales recibidos desde Unity, los guarda, los
    procesa con Whisper y los elimina despues de la transcripcion.

    No conoce los detalles de ningun motor STT especifico.
    Solo conoce el contrato BaseSTTClient.

    Attributes:
        _stt_client: cliente STT que implementa BaseSTTClient.
    """

    def __init__(self, stt_client: BaseSTTClient) -> None:
        """
        Inicializa el servicio con el cliente STT inyectado.
        
        Args:
            stt_client: implementacion de BaseSTTClient a usar.
                Puede ser FasterWhisperClient u otra implementacion futura.
        """
        self._stt_client = stt_client

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        context_hint: str | None = None, # Nueva linea
    ) -> tuple[STTResult, str]:
        """
        Transcribe audio recibido desde Unity a texto.
        
        Guarda los bytes de audio en un archivo temporal,
        los transcribe con el cliente STT y devuelve el resultado
        junto con la ruta del archivo temporal para que
        la capa API pueda eliminarlo despues de responder.

        Args:
            audio_bytes: bytes del archivo de audio enviado
                por el cliente (Unity) via HTTP.
            language: codigo de idioma opcional para forzar
                la transcripcion. Si es None, Whisper
                detecta el idioma automaticamente.
            context_hint: pista de contexto para mejorar la transcripcion.
        Returns:
            Tupla de (STTResult con la transcipcion,
            stt con la ruta del archivo temporal).

        Raises:
            RuntimeError: si el cliente STT falla al transcribir el audio.
            ValueError: si audio_bytes esta vacio.
        """
        if not audio_bytes:
            raise ValueError(
                "Los bytes de audio recibidos estan vacios. "
                "Verifica que el cliente (Unity) esta enviando el audio correctamente."
            )
        
        audio_path = self._save_audio_to_temp_file(audio_bytes)

        try:
            result = self._stt_client.transcribe(
                audio_path=audio_path,
                language=language,
                context_hint=context_hint,
            )
        except Exception as error:
            # Si la transcripcion falla, eliminamos el archivo
            # temporal antes de propagar mas el error
            self._delete_temp_file(audio_path)
            raise RuntimeError(
                f"Error al transcribir audio con el motor "
                f"'{self._stt_client.get_engine_name()}': {error}"
            ) from error
        
        return result, audio_path
    
    def get_active_engine(self) -> str:
        """
        Retorna el nombre del motor STT actualmente activo.
        
        Returns:
            Nombre del motor. Ejemplo: faster_whisper.
        """
        return self._stt_client.get_engine_name()
    
    def get_supported_languages(self) -> list[str]:
        """
        Retorna los idiomas soportados por el motor STT activo.
        
        Returns:
            Lista de codigos de idioma ISO 639-1.
        """
        return self._stt_client.get_supported_languages()
    
    def _save_audio_to_temp_file(self, audio_bytes: bytes) -> str:
        """
        Guarda los bytes de audio en un archivo temporal en disco.
        
        Genera un nombre unico con UUID para evitar colisiones
        entre peticiones simultaneas. Crea el directorio
        temporal si no existe.

        Args:
            audio_bytes: bytes del archivo de audio a guardar.

        Returns:
            Ruta completa del archivo temporal creado.
        """
        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

        unique_filename = f"{uuid.uuid4()}{AUDIO_FILE_EXTENSION}"
        audio_path = os.path.join(TEMP_AUDIO_DIR, unique_filename)

        with open(audio_path, "wb") as audio_file:
            audio_file.write(audio_bytes)

        return audio_path
    
    def _delete_temp_file(self, file_path: str) -> None:
        """
        Elimina un archivo temporal de audio del disco.
        
        Metodo de soporte para la limpieza en caso de error
        durante la transcripcion de audio.

        Args:
            file_path: ruta del archivo a eliminar.

        Returns:
            None.
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError as error:
            print(f"Advertencia: no se pudo eliminar {file_path}: {error}")