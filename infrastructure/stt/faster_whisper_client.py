# infrastructure/stt/faster_whisper_client.py
# =============================================================
# Implementacion del cliente STT usando Faster Whisper.
#
# Responsabilidad: cargar el modelo Whisper en memoria y
# transcribir archivos de audio a texto. Esconde toda la
# complejidad de faster-whisper detras de una interfaz simple.
#
# Patron: Strategy — implementacion concreta de BaseSTTClient.
# Patron: Facade — interfaz simple sobre la API de faster-whisper.

# Principio S de SOLID — unica responsabilidad: transcribir
# audio con Faster Whisper. No sabe nada de HTTP ni de
# logica de negocio.
# =============================================================

import os
import time
from faster_whisper import WhisperModel
from infrastructure.stt.base_stt_client import BaseSTTClient
from models.stt_result import STTResult
from config.settings import settings

# Nombre identificador de este motor STT
ENGINE_NAME = "faster_whisper"

# Tipo de computo optimizado para CPU.
# int8 reduce el uso de RAM y acelera inferencia sin
# perdida significativa de precision en transcripcion.
COMPUTE_TYPE = "int8"

# Dispositivo de inferencia.
# Cambiar a "cuda" si el servidor tiene GPU NVIDIA disponible.
DEVICE = "cpu"

# Idiomas soportados por Whisper.
# Lista reducia a los mas relevantes para el proyecto.
# Whisper soporta 99 idiomas en total.
SUPPORTED_LANGUAGES = [
    "es",  # Espaniol
    "en",  # Ingles
    "fr",  # Frances
    "de",  # Aleman
    "pt",  # Portugues
    "it",  # Italiano
    "ja",  # Japones
    "zh",  # Chino
]

class FasterWhisperClient(BaseSTTClient):
    """
    Cliente de Speech-to-Text usando Faster Whisper
    
    Implementa el contrato de BaseSTTClient usando la libreria
    faster-whisper, que ejecuta el modelo Whisper de OpenAI
    con CTranslate2 para mayor velocidad de CPU.

    El modelo se carga en memoria al instancia el cliente
    y permanece cargado durante toda la vida del servidor.
    Esto evita el costo de carga en cada peticion.

    Attributes:
        _model: instancia del modelo WhisperModel de faster-whisper.
    """

    def __init__(self) -> None:
        """
        Inicializa el cliente cargando el modelo Whisper en memoria.
        
        Lee el nombre del modelo desde settings para respetar
        la configuracion centralizada del sistema.

        El modelo se descarga automaticamente desde Hugging Face
        si no esta en cache local.
        """
        self._model = WhisperModel(
            model_size_or_path=settings.whisper.model,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> STTResult:
        """
        Transcribe un archivo de audio a texto usando Faster Whisper.
            
        Mide el tiempo de procesamiento y construye un STTResult
        con el texto transcrito, el idioma detectado y las metricas.
        

        Args:
            audio_path: ruta al archivo de audio a transcribir.
                Soporta .wav, .mp3, .ogg entre otros.
            language: codigo de idioma para forzar la transcripcion.
                Si es None, Whisper detecta el idioma automaticamente.

        Returns:
            STTResult con texto, idioma detectado, confianza
            promedio y tiempo de procesamiento en milisegundos.

        Raise:
            FileNotFoundError: si audio_path no existe en disco.
            RuntimeError: si faster-whisper falla al transcribir.
        """
        self._validate_audio_file_exists(audio_path)

        start_time = time.perf_counter()

        # faster-whisper devuelve un generador de segmentos
        # y un objeto con info del audio (idioma detectado,
        # probabilidad de idioma, duracion, etc.)
        segments, audio_info = self._model.transcribe(
            audio=audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,
        )

        # Materializar el generador de segmentos para obtener
        # todo el texto y calcular la confianza promedio
        segments_list = list(segments)

        transcribed_text = self._build_full_text(segments_list)
        average_confidence = self._calculate_average_confidence(segments_list)

        processing_time_ms = (time.perf_counter() - start_time) * 1000

        return STTResult(
            text=transcribed_text,
            language=audio_info.language,
            confidence=average_confidence,
            processing_time_ms=round(processing_time_ms, 2),
        )
        
    def get_engine_name(self) -> str:
        """
        Retorna el nombre identificador de este motor STT.
        
        Returns:
            String faster_whisper.
        """
        return ENGINE_NAME
        
    def get_supported_languages(self) -> list[str]:
        """
        Retorna la lista de codigos de idioma soportados.
        
        Returns: Lista de codigos de idioma ISO 639-1
        """
        return SUPPORTED_LANGUAGES.copy()
        
    def _validate_audio_file_exists(self, audio_path: str) -> None:
        """
        Verifica que el archivo de audio existe antes de transcribir.
        
        Falla rapido con un mensaje claro en lugar de dejar que
        faster-whisper falle con un error menos descriptivo.

        Args:
            audio_path: ruta al archivo de audio a verificar.

        Raises:
            FileNotFoundError: si el archivo no existe en disco.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(
                f"Archivo de audio no encontrado: '{audio_path}'."
                f"Verifica que el cliente (Unity) envio el archivo correctamente."
            )
        
    def _build_full_text(self, segments: list) -> str:
        """
        Construye el texto completo uniendo todos los segementos.
            
        faster-whisper divide la transcripcion en segmentos temporales.
        Este metodo los une en un solo string limpio.

        Args:
            segments: lista de segmentos de transcripcion
                devueltos por faster-whisper.
            
        Returns:
            Texto completo transcrito como un solo string.
        """
        return " ".join(segment.text.strip() for segment in segments)
        
    def _calculate_average_confidence(self, segments: list) -> float | None:
        """
        Calcula la confianza promedio de todos los segmentos.
        
        Cada segmento de faster-whisper tiene un campo avg_logprob
        que representa la probabilidad logaritmica promedio.
        Se convierte a un valor entre 0.0 y 1.0 para facilitar
        su interpretacion.

        Args:
            segments: lista de segmentos de transcripcion.

        Returns:
            Confianza promedio entre 0.0 y 1.0, o None si
            no hay segementos disponibles.
        """
        if not segments:
            return None
            
        # avg_logprob es negativo (log probability).
        # Un valor cercano a 0 muestra una alta confianza.
        # Convertimos a escala 0-1 usando exponencial.
        import math
        avg_logprob = sum(s.avg_logprob for s in segments) / len(segments)
        confidence = math.exp(avg_logprob)

        # Esta seguro de que el valor este dentro del rango valido
        return round(max(0.0, min(1.0, confidence)), 4)
