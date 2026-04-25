# infrastructure/stt/base_stt_client.py
# =============================================================
# Contrato base para todos los motores de Speech-to-Text.
#
# Responsabilidad: definir la interfaz que cualquier motor STT
# debe implementar para ser intercambiable en el sistema.
#
# Patron: Strategy — este es el contrato de la estrategia STT.

# Principio O de SOLID — agregar un nuevo motor STT solo
# requiere crear una nueva subclase sin modificar nada mas.

# Principio D de SOLID — las capas superiores dependen de
# esta abstraccion, nunca de implementaciones concretas.
# =============================================================

from abc import ABC, abstractmethod
from models.stt_result import STTResult

class BaseSTTClient(ABC):
    """
    Clase abstracta base para clientes de Speech-to-Text (STT).
    
    Define el contrato que cualquier motor STT debe cumplir
    para ser usado por STTService. Actua como la estrategia
    base en el patron Strategy, igual que BaseTTSClient
    cumple ese rol para subsitema TTS.
    
    Cualquier clase que here de BaseSTTCliente debe
    implementar todos los metodos abstractos, de lo contrario
    Python lanzara un error al intentar instanciarla.
    """

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> STTResult:
        """
        Transcribe un archivo de audio a texto.
        
        Este metodo es el nucleo del contrato STT. Cada motor
        implementara su porpia logica aqui, pero la firma
        siempre sera la misma para todas las implementaciones.
        
        Args:
            audio_path: ruta completa al archivo de audio
                a transcribir. Formatos soportados
                dependen de cada implementacion.
        
            language: codigo de idioma para formar la
                transcripcion. Ej: 'es', 'en'.
                Si es None, el motor detecta el idioma
                automaticamente.

        Returns:
            STTResult con el texto transcrito, el idioma
            detectado y metricas de procesamiento.

        Raises:
            FileNotFoundError: si audio_path no existe.
            RuntimeError: si el motor falla al transcribir.
        """
        pass

    @abstractmethod
    def get_engine_name(self) -> str:
        """
        Retorna el nombre identificador del motor STT que se este usando.

        Usado para logging y para informar al sistema
        que motor esta activo actualmente.
        
        Returns:
            Nombre del motor. Ejemplo: faster_whisper.
        """
        pass

    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        """
        Retorna la lista de codigos de idiomas que soporta.
        
        Permite que el sistema informa a Unity que idiomas
        puede transcribir el motor activo.
        
        Returns:
            Lista de codigos de idioma. Ejemplo: ['es', 'en', 'fr'].
        """
        pass